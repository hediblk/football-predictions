import pandas as pd
import pytest

from standing_prediction import site_history
from standing_prediction.data import rewind_season, standings_from_matches, validate_schedule

TEAMS = ["Alpha", "Bravo", "Charlie"]


def season():
    """A finished three-team double round robin, one match a day from 1 September."""
    rows, day = [], pd.Timestamp("2026-09-01 15:00", tz="UTC")
    scores = iter([(2, 0), (1, 1), (0, 1), (3, 2), (0, 0), (1, 2)])
    for home in TEAMS:
        for away in TEAMS:
            if home != away:
                hg, ag = next(scores)
                rows.append({"utcDate": day, "status": "FINISHED", "reported_status": "FINISHED",
                             "homeTeam": home, "awayTeam": away, "homeGoals": hg, "awayGoals": ag})
                day += pd.Timedelta(days=1)
    return pd.DataFrame(rows)


def test_rewind_hides_results_until_three_hours_after_kickoff():
    matches = season()
    table = standings_from_matches(matches, teams=TEAMS)
    rewound, rewound_table, adjustments = rewind_season(matches, table, "2026-09-02 17:59", competition="PL")
    assert rewound["status"].eq("FINISHED").sum() == 1  # the 15:00 kickoff on 2 September is not yet in
    assert rewound.loc[1, "reported_status"] == "SCHEDULED" and pd.isna(rewound.loc[1, "homeGoals"])
    assert adjustments == {}
    assert rewound_table.set_index("team").loc["Alpha", ["played", "points", "goals_for"]].tolist() == [1, 3, 2]
    assert rewound_table["position"].tolist() == [1, 2, 3] and rewound_table["team"].iloc[0] == "Alpha"
    assert len(validate_schedule(rewound, rewound_table)) == 5
    assert matches["status"].eq("FINISHED").all()  # input untouched


def test_rewind_carries_point_deductions_back():
    matches = season()
    table = standings_from_matches(matches, teams=TEAMS)
    table.loc[table["team"].eq("Alpha"), "points"] -= 6
    _, rewound_table, adjustments = rewind_season(matches, table, "2026-09-03 00:00", competition="PL")
    assert adjustments == {"Alpha": -6}
    assert rewound_table.set_index("team").loc["Alpha", "points"] == 4 - 6
    assert rewound_table["team"].iloc[-1] == "Alpha"


def league(cutoff, title=50.0, season_label="2026/27"):
    return {"slug": "premier-league", "kind": "league", "season": season_label, "data_cutoff": cutoff, "teams": [
        {"id": 57, "slug": "arsenal", "name": "Arsenal", "title": title, "ucl": 90.04, "releg": 0},
        {"id": 65, "slug": "man-city", "name": "Man City", "title": 100 - title, "ucl": 80, "releg": 0},
    ]}


def test_a_point_is_added_per_results_day_and_updated_otherwise():
    history = site_history.add_point(None, league(None), "2026-08-21")
    history = site_history.add_point(history, league(None, 51), "2026-08-22")  # no results yet: same point
    assert history["dates"] == ["2026-08-21"] and history["teams"][0]["title"] == [51.0]
    history = site_history.add_point(history, league("2026-08-22T19:00:00+00:00", 55), "2026-08-23")
    history = site_history.add_point(history, league("2026-08-22T19:00:00+00:00", 56), "2026-08-24")
    assert history["dates"] == ["2026-08-21", "2026-08-23"]
    assert history["teams"][0]["title"] == [51.0, 56.0] and history["teams"][0]["ucl"] == [90.0, 90.0]
    with pytest.raises(ValueError):
        site_history.add_point(history, league("2026-08-25T19:00:00+00:00"), "2026-08-20")
    fresh = site_history.add_point(history, league(None, season_label="2027/28"), "2027-08-20")
    assert fresh["dates"] == ["2027-08-20"]


def test_new_teams_are_padded_and_ucl_stages_are_cumulative():
    data = {"slug": "champions-league", "kind": "ucl", "season": "2026/27", "data_cutoff": None, "teams": [
        {"id": 5, "slug": "bayern", "name": "Bayern", "r16": 40, "playoff": 50, "title": 12,
         "stages": {"round16": 70, "quarterfinal": 45, "semifinal": 28, "final": 18}}]}
    history = site_history.add_point(None, data, "2026-09-01")
    assert history["metrics"] == list(site_history.UCL_METRICS)
    assert [history["teams"][0][metric][0] for metric in history["metrics"]] == [40, 90, 70, 45, 28, 18, 12]
    data = {**data, "data_cutoff": "2026-09-10T21:00:00+00:00",
            "teams": data["teams"] + [{**data["teams"][0], "id": None, "slug": "newcomer", "name": "Newcomer"}]}
    history = site_history.add_point(history, data, "2026-09-11")
    assert history["teams"][1]["id"] == "newcomer" and history["teams"][1]["title"] == [None, 12]


def test_merge_keeps_refresh_points_after_the_backfill():
    backfill = site_history.add_point(None, league(None, 40), "2026-08-21")
    backfill = site_history.add_point(backfill, league("2026-08-22T19:00:00+00:00", 45), "2026-08-23")
    refresh = site_history.add_point(None, league("2026-08-22T19:00:00+00:00", 46), "2026-08-23")
    refresh = site_history.add_point(refresh, league("2026-08-29T19:00:00+00:00", 60), "2026-08-30")
    merged = site_history.merge_points(backfill, refresh)
    assert merged["dates"] == ["2026-08-21", "2026-08-23", "2026-08-30"]
    assert merged["teams"][0]["title"] == [40, 45, 60] and merged["cutoff"] == "2026-08-29T19:00:00+00:00"
    assert site_history.merge_points(backfill, None) is backfill


def test_the_week_is_frozen_once_by_tuesday_morning():
    ratings = {57: (61.234, 58.0, 64.0)}
    history, added = site_history.freeze_week(None, ratings, as_of="2026-10-12T05:30Z", season="2026/27")
    assert added and history["weeks"] == [{"date": "2026-10-12", "cutoff": None, "clubs": {"57": [61.2, 58.0, 64.0]}}]
    history, added = site_history.freeze_week(history, {57: (70, 70, 70)}, as_of="2026-10-13T05:30Z", season="2026/27")
    assert not added and history["weeks"][-1]["clubs"]["57"][0] == 61.2
    _, added = site_history.freeze_week(None, ratings, as_of="2026-10-14T05:30Z", season="2026/27")
    assert not added  # Wednesday's ratings already include Tuesday's Champions League games
    history, added = site_history.freeze_week(history, ratings, as_of="2026-10-20T05:30Z", season="2026/27")
    merged = site_history.merge_weeks({"season": "2026/27", "weeks": history["weeks"][:1]}, history)
    assert added and [week["date"] for week in merged["weeks"]] == ["2026-10-12", "2026-10-19"]


def test_backfill_reruns_on_the_first_refresh_to_see_each_result():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "scripts" / "backfill_history.py"
    spec = importlib.util.spec_from_file_location("backfill_history", path)
    backfill = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backfill)
    kickoffs = ["2026-08-21T19:00Z", "2026-08-22T11:30Z", "2026-08-22T14:00Z", "2026-08-24T02:30Z", "2026-09-30T19:00Z"]
    # 22:00 → next morning; 14:30 and 17:00 → the 23rd; 05:30 exactly → that morning's refresh
    assert backfill.result_days(kickoffs, "2026-09-01") == ["2026-08-21", "2026-08-22", "2026-08-23", "2026-08-24"]
    assert backfill.mondays("2026-08-15", "2026-08-31") == ["2026-08-17", "2026-08-24", "2026-08-31"]


def test_chances_keep_a_decimal_only_below_ten():
    assert [site_history.chance(v) for v in (0, 0.04, 0.35, 9.96, 10.4, 52.5, 99.6, None)] == [0, 0, 0.3, 10, 10, 53, 100, None]
