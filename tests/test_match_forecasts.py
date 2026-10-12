import numpy as np
import pandas as pd
import pytest

from standing_prediction.club_ratings import club_ratings, points_share
from standing_prediction.defaults import DEFAULT_WEIGHTS
from standing_prediction.dixon_coles import DixonColesModel, score_matrix_from_rates
from standing_prediction.match_forecasts import describe_match, scoreline_distribution
from standing_prediction.predict_positions import season_match_forecasts

TEAMS = ["Alpha", "Bravo", "Charlie", "Delta"]


def round_robin(start, seed=0, status="FINISHED"):
    rng = np.random.default_rng(seed)
    rows, day = [], pd.Timestamp(start, tz="UTC")
    for home in TEAMS:
        for away in TEAMS:
            if home != away:
                gap = TEAMS.index(away) - TEAMS.index(home)
                rows.append({"utcDate": day, "status": status, "homeTeam": home, "awayTeam": away,
                             "homeGoals": int(rng.poisson(1.4 + 0.2 * gap)), "awayGoals": int(rng.poisson(1.1 - 0.1 * gap))})
                day += pd.Timedelta(days=3)
    return pd.DataFrame(rows)


def test_scoreline_distribution_carries_the_blended_outcome_probabilities():
    _, matrix = score_matrix_from_rates(1.6, 0.9, -0.05)
    dist = scoreline_distribution(matrix, (0.5, 0.3, 0.2))
    home, away = np.indices(dist.shape)
    assert dist.sum() == pytest.approx(1)
    assert [dist[home > away].sum(), dist[home == away].sum(), dist[home < away].sum()] == pytest.approx([0.5, 0.3, 0.2])
    # Within an outcome, scorelines keep the goal model's relative weights.
    assert dist[2, 1] / dist[1, 0] == pytest.approx(matrix[2, 1] / matrix[1, 0])


def test_describe_match_summarises_the_distribution():
    _, matrix = score_matrix_from_rates(1.8, 0.7, 0.0)
    out = describe_match(matrix, (0.6, 0.25, 0.15), score=(2, 1))
    probs = [p for _, _, p in out["scorelines"]]
    assert probs == sorted(probs, reverse=True) and len(probs) == 4
    assert out["exp_home_goals"] > out["exp_away_goals"]
    assert 0 < out["btts"] < 1 and 0 < out["over_2_5"] < 1
    assert out["p_score"] == pytest.approx(scoreline_distribution(matrix, (0.6, 0.25, 0.15))[2, 1])
    assert describe_match(matrix, (0.6, 0.25, 0.15), score=(15, 0))["p_score"] == 0


def test_pick_score_agrees_with_the_picked_outcome():
    # Close teams: 1-1 is the single likeliest score, but a home win is the likeliest outcome.
    _, matrix = score_matrix_from_rates(1.3, 1.1, 0.0)
    out = describe_match(matrix, (0.42, 0.30, 0.28))
    assert out["scorelines"][0][:2] == [1, 1]
    home, away, p = out["pick_score"]
    assert home > away
    dist = scoreline_distribution(matrix, (0.42, 0.30, 0.28))
    assert p == pytest.approx(dist[home, away]) == pytest.approx(max(dist[h, a] for h in range(dist.shape[0]) for a in range(h)))


def test_played_matches_are_forecast_only_from_earlier_results():
    history = round_robin("2024-08-01", seed=1)
    season = round_robin("2025-08-01", seed=2)
    season.loc[8:, ["status", "homeGoals", "awayGoals"]] = ["SCHEDULED", None, None]
    options = dict(teams=TEAMS, history=history, current_models=None, cutoff=pd.Timestamp("2025-09-01", tz="UTC"),
                   weights=DEFAULT_WEIGHTS, xg_weight=0)
    before = season_match_forecasts(season, **options)
    changed = season.copy()
    changed.loc[7, ["homeGoals", "awayGoals"]] = [9, 0]  # the last played match
    after = season_match_forecasts(changed, **options)
    played = [i for i, row in enumerate(before) if row["status"] == "FINISHED"]
    assert len(played) == 8
    for i in played:
        assert before[i]["p_home"] == pytest.approx(after[i]["p_home"])
        assert before[i]["forecast_at"] == pd.Timestamp(season.at[i, "utcDate"]).floor("D").isoformat()
    assert "p_home" not in before[10]  # unplayed fixtures need the current models


def model(attack, defense, home_advantage=0.25):
    teams = tuple(f"T{i}" for i in range(len(attack)))
    return DixonColesModel(teams=teams, team_index={t: i for i, t in enumerate(teams)}, intercept=0.3,
                           home_advantage=home_advantage, attack=np.array(attack, float),
                           defense=np.array(defense, float), rho=-0.05, xi=0.003, fitted_at=pd.Timestamp("2026-01-01"))


def test_club_ratings_share_one_scale():
    dc = model([0.3, 0.3, 0.0, -0.6], [-0.3, 0.1, 0.0, 0.2])
    ratings = club_ratings(dc, list(dc.teams)).set_index("team")
    balanced, attacking = ratings.loc["T0"], ratings.loc["T1"]
    # A club as far above average at both ends gets the same three numbers.
    assert balanced[["attack_rating", "defense_rating"]].tolist() == pytest.approx([balanced["rating"]] * 2, abs=1e-9)
    assert attacking["defense_rating"] < attacking["rating"] < attacking["attack_rating"]
    assert ratings.loc["T0", "rating"] > ratings.loc["T3", "rating"]
    assert ratings.loc["T0", "home_rating"] > ratings.loc["T0", "rating"] > ratings.loc["T0", "away_rating"]


def test_points_share_of_an_even_match_counts_draws_once():
    share = points_share(0.0, 0.0, 0.0, 0.0, intercept=0.3, rho=-0.05)
    _, matrix = score_matrix_from_rates(np.exp(0.3), np.exp(0.3), -0.05)
    home, away = np.indices(matrix.shape)
    assert share == pytest.approx(100 * (1 + matrix[home > away].sum()) / 3)
