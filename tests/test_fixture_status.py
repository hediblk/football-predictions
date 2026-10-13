import pandas as pd
import pytest

from standing_prediction.data import OVERRIDE_COLUMNS, fill_lagging_results, resolve_fixture_statuses, validate_schedule

TEAMS = ["Alpha", "Bravo", "Charlie"]


def schedule(status_by_pair=None, scores=None):
    status_by_pair, scores = status_by_pair or {}, scores or {}
    rows = []
    day = pd.Timestamp("2026-08-15", tz="UTC")
    for home in TEAMS:
        for away in TEAMS:
            if home != away:
                status = status_by_pair.get((home, away), "SCHEDULED")
                goals = scores.get((home, away), (None, None))
                rows.append({"utcDate": day, "status": status, "homeTeam": home, "awayTeam": away,
                             "homeGoals": goals[0], "awayGoals": goals[1]})
                day += pd.Timedelta(days=1)
    return pd.DataFrame(rows)


def overrides(*rows):
    return pd.DataFrame([dict(zip(OVERRIDE_COLUMNS, ["PD", 2026, *row])) for row in rows], columns=OVERRIDE_COLUMNS)


def empty_standings():
    return pd.DataFrame({"position": [1, 2, 3], "team": TEAMS, "played": 0, "goals_for": 0, "goals_against": 0})


def test_cancelled_fixture_is_simulated_and_reported():
    matches = schedule({("Alpha", "Bravo"): "CANCELLED"})
    with pytest.warns(UserWarning, match="replayed"):
        resolved, adjustments = resolve_fixture_statuses(matches)
    row = resolved[resolved.homeTeam.eq("Alpha") & resolved.awayTeam.eq("Bravo")].iloc[0]
    assert (row.status, row.reported_status) == ("SCHEDULED", "CANCELLED")
    assert matches.status.eq("CANCELLED").sum() == 1  # input untouched
    assert adjustments[0]["used_status"] == "SCHEDULED"
    assert len(validate_schedule(resolved, empty_standings())) == 6


def test_strict_mode_rejects_cancelled_fixture():
    with pytest.raises(ValueError, match="strict"):
        resolve_fixture_statuses(schedule({("Alpha", "Bravo"): "CANCELLED"}), strict=True)


def test_awarded_fixture_with_score_counts_as_played():
    matches = schedule({("Alpha", "Bravo"): "AWARDED"}, {("Alpha", "Bravo"): (3, 0)})
    with pytest.warns(UserWarning):
        resolved, adjustments = resolve_fixture_statuses(matches)
    assert resolved.status.eq("FINISHED").sum() == 1
    assert adjustments[0]["score"] == "3-0"


def test_awarded_fixture_without_score_needs_override():
    with pytest.raises(ValueError, match="overrides"):
        resolve_fixture_statuses(schedule({("Alpha", "Bravo"): "AWARDED"}))


def test_override_takes_precedence_over_cancelled_status():
    matches = schedule({("Alpha", "Bravo"): "CANCELLED"})
    with pytest.warns(UserWarning, match="override: awarded by league"):
        resolved, adjustments = resolve_fixture_statuses(matches, overrides(("Alpha", "Bravo", "FINISHED", 0, 3, "awarded by league")))
    row = resolved[resolved.homeTeam.eq("Alpha") & resolved.awayTeam.eq("Bravo")].iloc[0]
    assert (row.status, row.homeGoals, row.awayGoals) == ("FINISHED", 0, 3)
    assert len(adjustments) == 1


def test_override_must_match_one_fixture_and_have_a_score():
    with pytest.raises(ValueError, match="matches 0 fixtures"):
        resolve_fixture_statuses(schedule(), overrides(("Alpha", "Zulu", "SCHEDULED", None, None, "")))
    with pytest.raises(ValueError, match="needs both scores"):
        resolve_fixture_statuses(schedule(), overrides(("Alpha", "Bravo", "FINISHED", 1, None, "")))


def test_untouched_schedule_has_no_adjustments():
    resolved, adjustments = resolve_fixture_statuses(schedule())
    assert adjustments == [] and resolved.status.eq(resolved.reported_status).all()


def table_after_alpha_bravo(home_goals=2, away_goals=1):
    """The provider's table once Alpha 2-1 Bravo (15 August) counts, while the fixture still reads TIMED."""
    return pd.DataFrame({"position": [1, 2, 3], "team": TEAMS, "played": [1, 1, 0],
                         "goals_for": [home_goals, away_goals, 0], "goals_against": [away_goals, home_goals, 0]})


def understat(home="Alpha", away="Bravo", score=(2, 1), day="2026-08-15"):
    return pd.DataFrame({"homeTeam": [home], "awayTeam": [away], "utcDate": [pd.Timestamp(day, tz="UTC")],
                         "homeGoals": [score[0]], "awayGoals": [score[1]]})


def test_lagging_fixture_is_filled_when_the_table_already_counts_it():
    matches = schedule({("Alpha", "Bravo"): "TIMED"})
    with pytest.warns(UserWarning, match="Understat"):
        filled, adjustments = fill_lagging_results(matches, table_after_alpha_bravo(), understat(), as_of="2026-08-20")
    row = filled[filled.homeTeam.eq("Alpha") & filled.awayTeam.eq("Bravo")].iloc[0]
    assert (row.status, row.reported_status, row.homeGoals, row.awayGoals) == ("FINISHED", "TIMED", 2, 1)
    assert adjustments[0]["score"] == "2-1"
    assert len(validate_schedule(filled, table_after_alpha_bravo())) == 5


def test_lagging_fill_needs_a_past_kickoff_the_table_and_a_matching_result():
    matches = schedule({("Alpha", "Bravo"): "TIMED"})
    calls = []
    unused, adjustments = fill_lagging_results(matches, empty_standings(), lambda: calls.append(1), as_of="2026-08-20")
    assert adjustments == [] and calls == []  # nothing lags, so the second source is not fetched
    for kwargs in ({"results": understat(), "as_of": "2026-08-14"},
                   {"results": understat(day="2026-09-30"), "as_of": "2026-08-20"},
                   {"results": understat(home="Charlie", away="Alpha"), "as_of": "2026-08-20"},
                   {"results": None, "as_of": "2026-08-20"}):
        unchanged, adjustments = fill_lagging_results(matches, table_after_alpha_bravo(), **kwargs)
        assert adjustments == [] and unchanged.status.eq("FINISHED").sum() == 0
    with pytest.raises(ValueError, match="disagree"):
        validate_schedule(unchanged, table_after_alpha_bravo())


def test_filled_score_that_contradicts_the_table_is_still_rejected():
    matches = schedule({("Alpha", "Bravo"): "TIMED"})
    with pytest.warns(UserWarning):
        filled, _ = fill_lagging_results(matches, table_after_alpha_bravo(), understat(score=(0, 0)), as_of="2026-08-20")
    with pytest.raises(ValueError, match="goals_for"):
        validate_schedule(filled, table_after_alpha_bravo())
