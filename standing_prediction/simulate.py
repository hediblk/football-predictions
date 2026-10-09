from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FixtureSimulationSpec:
    home: str
    away: str
    p_home_win: float
    p_draw: float
    p_away_win: float
    scorelines: np.ndarray  # shape (n_scores, 2) int
    score_probs_by_outcome: tuple[np.ndarray, np.ndarray, np.ndarray]  # each shape (n_scores,)


def simulate_season(
    fixtures,
    standings,
    n_sim=5000,
    seed=None,
):
    rng = np.random.default_rng(seed)
    teams = standings["team"].tolist()
    positions = list(range(1, len(teams) + 1))
    counts = pd.DataFrame(0, index=teams, columns=positions)

    base_points = dict(zip(standings["team"], standings["points"]))
    base_gd = dict(zip(standings["team"], standings["goal_diff"]))
    team_count = len(teams)

    for _ in range(n_sim):
        points = base_points.copy()
        goal_diff = base_gd.copy()
        for _, row in fixtures.iterrows():
            probs = np.array([row["p_home_win"], row["p_draw"], row["p_away_win"]], dtype=float)
            probs = probs / probs.sum()
            outcome = rng.choice(3, p=probs)
            home = row["homeTeam"]
            away = row["awayTeam"]
            if outcome == 0:
                points[home] += 3
            elif outcome == 1:
                points[home] += 1
                points[away] += 1
            else:
                points[away] += 3

        tie_break = rng.random(team_count)
        order = sorted(
            range(team_count),
            key=lambda i: (points[teams[i]], goal_diff[teams[i]], tie_break[i]),
            reverse=True,
        )
        for pos, idx in enumerate(order, start=1):
            counts.iat[idx, pos - 1] += 1 # type: ignore

    return counts


def simulate_season_scores(
    fixtures,
    standings,
    n_sim=3000,
    seed=None,
):
    rng = np.random.default_rng(seed)
    teams = standings["team"].tolist()
    positions = list(range(1, len(teams) + 1))
    counts = pd.DataFrame(0, index=teams, columns=positions)

    base_points = dict(zip(standings["team"], standings["points"]))
    base_gf = dict(zip(standings["team"], standings["goals_for"]))
    base_ga = dict(zip(standings["team"], standings["goals_against"]))
    team_count = len(teams)

    for _ in range(n_sim):
        points = base_points.copy()
        gf = base_gf.copy()
        ga = base_ga.copy()

        for fx in fixtures:
            probs = np.array([fx.p_home_win, fx.p_draw, fx.p_away_win], dtype=float)
            probs = probs / probs.sum()
            outcome = int(rng.choice(3, p=probs))

            score_probs = fx.score_probs_by_outcome[outcome]
            if float(score_probs.sum()) <= 0:
                score_probs = np.ones_like(score_probs) / len(score_probs)
            idx = int(rng.choice(len(fx.scorelines), p=score_probs))
            home_goals = int(fx.scorelines[idx, 0])
            away_goals = int(fx.scorelines[idx, 1])

            gf[fx.home] += home_goals
            ga[fx.home] += away_goals
            gf[fx.away] += away_goals
            ga[fx.away] += home_goals

            if home_goals > away_goals:
                points[fx.home] += 3
            elif home_goals == away_goals:
                points[fx.home] += 1
                points[fx.away] += 1
            else:
                points[fx.away] += 3

        tie_break = rng.random(team_count)
        order = sorted(
            range(team_count),
            key=lambda i: (
                points[teams[i]],
                (gf[teams[i]] - ga[teams[i]]),
                gf[teams[i]],
                tie_break[i],
            ),
            reverse=True,
        )
        for pos, idx in enumerate(order, start=1):
            counts.iat[idx, pos - 1] += 1 # type: ignore

    return counts
