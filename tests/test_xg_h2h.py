import numpy as np
import pandas as pd
import pytest

from standing_prediction.dixon_coles import fit_dixon_coles
from standing_prediction.h2h import encounter_residuals, h2h_shifts, pair_effects
from standing_prediction.predict_positions import adjust_goal_model
from standing_prediction.xg import attach_xg, blend_xg_strengths, fit_xg_strengths

TEAMS = ["Alpha", "Bravo", "Charlie", "Delta"]


def round_robin(start, seasons=1, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    day = pd.Timestamp(start, tz="UTC")
    for _ in range(seasons):
        for home in TEAMS:
            for away in TEAMS:
                if home != away:
                    strength = TEAMS.index(away) - TEAMS.index(home)
                    rows.append({"utcDate": day, "homeTeam": home, "awayTeam": away,
                                 "homeGoals": int(rng.poisson(1.4 + 0.2 * strength)),
                                 "awayGoals": int(rng.poisson(1.1 - 0.1 * strength))})
                    day += pd.Timedelta(days=3)
    out = pd.DataFrame(rows)
    out["home_xg"] = out["homeGoals"] * 0.8 + 0.3
    out["away_xg"] = out["awayGoals"] * 0.8 + 0.3
    return out


def test_attach_xg_rejects_score_and_kickoff_mismatches():
    results = pd.DataFrame({
        "utcDate": pd.to_datetime(["2024-08-01 18:00", "2024-08-02 18:00", "2024-08-03 18:00"], utc=True),
        "homeTeam": ["Alpha", "Bravo", "Charlie"], "awayTeam": ["Bravo", "Charlie", "Alpha"],
        "homeGoals": [1, 2, 0], "awayGoals": [0, 2, 0],
    })
    xg = pd.DataFrame({
        "utcDate": pd.to_datetime(["2024-08-01 18:00", "2024-08-02 18:00", "2024-08-09 18:00"], utc=True),
        "homeTeam": ["Alpha", "Bravo", "Charlie"], "awayTeam": ["Bravo", "Charlie", "Alpha"],
        "homeGoals": [1, 1, 0], "awayGoals": [0, 2, 0], "home_xg": [1.5, 0.9, 0.4], "away_xg": [0.2, 1.1, 0.6],
    })
    out = attach_xg(results, xg)
    assert out["home_xg"].tolist()[0] == 1.5
    assert out[["home_xg", "away_xg"]].iloc[1:].isna().all().all()
    coverage = out.attrs["xg_coverage"]
    assert (coverage["matched"], coverage["score_mismatch"], coverage["kickoff_mismatch"]) == (1, 1, 1)


def test_residual_baseline_ignores_the_match_and_later_results():
    results = round_robin("2020-08-01", seasons=6)
    base = encounter_residuals(results, refit_days=28, min_matches=12, cache_dir=None)
    target = results.index[-5]
    changed = results.copy()
    changed.loc[target:, ["homeGoals", "awayGoals"]] = [9, 0]
    after = encounter_residuals(changed, refit_days=28, min_matches=12, cache_dir=None)
    when = results.at[target, "utcDate"]
    pd.testing.assert_series_equal(base.loc[base["utcDate"] <= when, "expected_diff"].reset_index(drop=True),
                                   after.loc[after["utcDate"] <= when, "expected_diff"].reset_index(drop=True))


def test_pair_effects_filter_at_origin_and_are_antisymmetric():
    residuals = pd.DataFrame({
        "utcDate": pd.to_datetime(["2024-01-01", "2024-06-01", "2025-01-01"], utc=True),
        "home_key": ["bravo", "alpha", "alpha"], "away_key": ["alpha", "bravo", "bravo"],
        "goal_diff": [0, 2, 5], "expected_diff": [1.0, 0.0, 0.0], "residual": [-1.0, 2.0, 5.0],
    })
    effects = pair_effects(residuals, "2024-12-31", half_life_days=1e9, shrinkage=2.0)
    assert effects.iloc[0]["effect"] == pytest.approx((1.0 + 2.0) / (2.0 + 2.0))
    shifts = h2h_shifts(["Alpha", "Bravo"], effects, 0.1)
    assert shifts[("Alpha", "Bravo")] == pytest.approx(-shifts[("Bravo", "Alpha")])


def test_adjustments_are_identity_at_zero_and_shift_rates_in_opposite_directions():
    matches = round_robin("2023-08-01", seasons=2)
    dc = fit_dixon_coles(matches)
    xg = fit_xg_strengths(matches)
    assert adjust_goal_model(dc, teams=TEAMS, xg_strengths=xg, xg_weight=0.0) is dc
    full = blend_xg_strengths(dc, xg, 1.0)
    assert full.attack[full.team_index["Alpha"]] == pytest.approx(xg.attack["Alpha"])
    effects = pd.DataFrame({"team_a": ["alpha"], "team_b": ["bravo"], "effect": [0.5]})
    shifted = adjust_goal_model(dc, teams=TEAMS, h2h_effects=effects, h2h_weight=0.2)
    home, away = dc.expected_goals("Alpha", "Bravo")
    new_home, new_away = shifted.expected_goals("Alpha", "Bravo")
    assert new_home == pytest.approx(home * np.exp(0.1))
    assert new_away == pytest.approx(away * np.exp(-0.1))
    assert shifted.expected_goals("Charlie", "Delta") == dc.expected_goals("Charlie", "Delta")


def test_xg_fit_excludes_matches_at_or_after_reference_date():
    matches = round_robin("2023-08-01")
    cutoff = matches["utcDate"].iloc[6]
    before = fit_xg_strengths(matches, reference_date=cutoff)
    altered = matches.copy()
    altered.loc[6:, ["home_xg", "away_xg"]] = 5.0
    assert fit_xg_strengths(altered, reference_date=cutoff).attack == before.attack
    assert before.matches == 6
