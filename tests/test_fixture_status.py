import pandas as pd
import pytest

from standing_prediction.data import OVERRIDE_COLUMNS, resolve_fixture_statuses, validate_schedule

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
