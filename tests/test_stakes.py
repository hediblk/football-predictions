import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from standing_prediction.predict_positions import upcoming_fixtures
from standing_prediction.simulate import FixtureSimulationSpec, simulate_season_scores
from standing_prediction.stakes import fixture_stakes

TEAMS = ["Alpha", "Bravo", "Charlie", "Delta"]
SCORES = np.array([[1, 0], [0, 0], [0, 1]])
ONE_HOT = tuple(np.eye(3))


def spec(home, away, p):
    return FixtureSimulationSpec(home, away, *p, SCORES, ONE_HOT)


def standings():
    """Alpha and Bravo level on 10 points, Alpha ahead on goal difference; Charlie and Delta far behind."""
    return pd.DataFrame({"team": TEAMS, "points": [10, 10, 1, 0], "goals_for": [10, 8, 2, 1], "goals_against": [5, 5, 9, 9]})


def league(p_decider=(0.4, 0.2, 0.4)):
    return [spec("Alpha", "Bravo", p_decider), spec("Charlie", "Delta", (0.5, 0.25, 0.25)),
            spec("Delta", "Alpha", (0.3, 0.3, 0.4))]


def test_tracking_changes_nothing_else():
    plain = simulate_season_scores(league(), standings(), n_sim=500, seed=3)
    counts, points, details = simulate_season_scores(league(), standings(), n_sim=500, seed=3, track=[0, 1], return_details=True)
    pd.testing.assert_frame_equal(plain, counts)
    assert details["outcomes"].shape == (500, 2) and details["places"].shape == (500, 4)


def test_outcomes_follow_the_sampled_scores_and_places_rebuild_the_counts():
    n_sim = 800
    counts, _, details = simulate_season_scores(league(), standings(), n_sim=n_sim, seed=11, track=[0, 2])
    # The first fixture is the first draw from the generator.
    drawn = SCORES[np.random.default_rng(11).choice(3, size=n_sim, p=[0.4, 0.2, 0.4])]
    assert (details["outcomes"][:, 0] == np.where(drawn[:, 0] > drawn[:, 1], 0, np.where(drawn[:, 0] == drawn[:, 1], 1, 2))).all()
    places = details["places"]
    for position in range(4):
        assert np.bincount(np.where(places == position)[1], minlength=4).tolist() == counts.iloc[:, position].tolist()


def test_a_decisive_game_moves_the_title_to_the_winner_only():
    _, _, details = simulate_season_scores(league(), standings(), n_sim=2000, seed=5, track=[0])
    stakes = fixture_stakes(details["outcomes"], details["places"], TEAMS, top=2, releg_from=3)[0]
    assert sum(stakes["n"]) == 2000
    # Alpha stays ahead on goal difference after a draw and keeps the title; only a Bravo win hands it over.
    assert stakes["teams"]["Alpha"] == {"title": [100, 100, 0]}
    assert stakes["teams"]["Bravo"] == {"title": [0, 0, 100]}
    # Charlie and Delta can't change their place in the table whatever happens here (top two / bottom two are fixed).
    assert set(stakes["teams"]) == {"Alpha", "Bravo"}


def test_thin_results_are_hidden_and_small_swings_dropped():
    outcomes = np.repeat([0, 1, 2], [250, 100, 250])[:, None]  # the draw has under 200 simulations
    leader = np.where(outcomes[:, 0] == 2, 1, 0)  # Alpha leads unless the away side wins
    places = np.column_stack([leader, 1 - leader, np.full(600, 2)])
    stakes = fixture_stakes(outcomes, places, ["A", "B", "C"], top=1, releg_from=3)[0]
    assert stakes["n"] == [250, 100, 250]
    assert stakes["teams"]["A"] == {"title": [100, None, 0], "ucl": [100, None, 0]}
    assert stakes["teams"]["B"] == {"title": [0, None, 100], "ucl": [0, None, 100]}
    assert "C" not in stakes["teams"]  # always last: nothing at stake
    assert fixture_stakes(outcomes, places, ["A", "B", "C"], top=1, releg_from=3, min_swing=101)[0]["teams"] == {}


def test_a_chance_that_does_not_move_is_not_a_stake():
    outcomes = np.repeat([0, 1, 2], 300)[:, None]
    places = np.tile([0, 1], (900, 1))
    assert fixture_stakes(outcomes, places, ["A", "B"], top=1, releg_from=2)[0]["teams"] == {}


def test_next_round_is_the_kickoffs_within_a_week_else_the_earliest_matchday():
    cutoff = pd.Timestamp("2026-10-13 05:30", tz="UTC")
    day = lambda d: cutoff + pd.Timedelta(days=d)
    frame = pd.DataFrame({"utcDate": [day(10), day(2), day(3), day(9), day(30)], "matchday": [8, 7, 7, 8, 9]})
    assert upcoming_fixtures(frame, cutoff) == [1, 2]
    assert upcoming_fixtures(frame.iloc[[0, 3, 4]].reset_index(drop=True), cutoff) == [0, 1]  # break: the earliest matchday
    assert upcoming_fixtures(frame.drop(columns="matchday").iloc[[4, 3, 0]].reset_index(drop=True), cutoff, fallback=2) == [1, 2]


def build_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "build_site_data.py"
    spec_ = importlib.util.spec_from_file_location("build_site_data", path)
    module = importlib.util.module_from_spec(spec_)
    spec_.loader.exec_module(module)
    return module


def test_export_matches_attaches_stakes_to_upcoming_matches_by_id(tmp_path):
    forecast = {"generated_at": "2026-10-13T05:30:00+00:00", "matches": [
        {"id": 1, "utcDate": "2026-10-17T14:00:00+00:00", "matchday": 8, "status": "TIMED",
         "homeTeam": "Arsenal FC", "awayTeam": "Manchester City FC", "homeTeamId": 57, "awayTeamId": 65},
        {"id": 2, "utcDate": "2026-10-18T14:00:00+00:00", "matchday": 8, "status": "TIMED",
         "homeTeam": "Chelsea FC", "awayTeam": "Fulham FC", "homeTeamId": 61, "awayTeamId": 63},
    ]}
    snapshot = pd.DataFrame({"homeTeam": ["Arsenal FC", "Chelsea FC"], "awayTeam": ["Manchester City FC", "Fulham FC"],
                             "homeTeamId": [57, 61], "awayTeamId": [65, 63]})
    stakes = {"fixtures": [{"id": 1, "home": "Arsenal FC", "away": "Manchester City FC", "utcDate": "2026-10-17T14:00:00+00:00",
                            "n": [4000, 2500, 3500], "teams": {
                                "Arsenal FC": {"title": [60, 45, 20]},
                                "Manchester City FC": {"title": [20, 30, 50], "ucl": [90, 94, 99]}}}]}
    for name, content in {"pl_match_forecasts.json": json.dumps(forecast), "pl_stakes.json": json.dumps(stakes)}.items():
        (tmp_path / name).write_text(content)
    snapshot.to_csv(tmp_path / "pl_matches_snapshot.csv", index=False)
    module = build_script()
    matches = module.export_matches(tmp_path, "premier-league", "pl")["matches"]
    assert matches[0]["stakes"] == {"n": [4000, 2500, 3500], "teams": [
        {"id": 57, "name": "Arsenal", "title": [60, 45, 20]},  # the 40-point swing sorts first
        {"id": 65, "name": "Man City", "title": [20, 30, 50], "ucl": [90, 94, 99]}]}
    assert "stakes" not in matches[1]
    (tmp_path / "pl_stakes.json").unlink()
    assert all("stakes" not in match for match in module.export_matches(tmp_path, "premier-league", "pl")["matches"])
