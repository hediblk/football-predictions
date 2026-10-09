from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import poisson


@dataclass
class StrengthModel:
    attack: pd.Series
    defense: pd.Series
    league_home_avg: float
    league_away_avg: float
    max_goals: int = 6


def fit_strengths(matches):
    finished = matches.dropna(subset=["homeGoals", "awayGoals"]).copy()
    if finished.empty:
        raise ValueError("No finished matches available to fit the model.")
    teams = pd.unique(finished[["homeTeam", "awayTeam"]].values.ravel("K"))
    league_home_avg = finished["homeGoals"].mean()
    league_away_avg = finished["awayGoals"].mean()
    league_avg = (league_home_avg + league_away_avg) / 2

    attack = pd.Series(1.0, index=teams)
    defense = pd.Series(1.0, index=teams)

    for team in teams:
        home = finished[finished["homeTeam"] == team]
        away = finished[finished["awayTeam"] == team]
        games = len(home) + len(away)
        if games == 0:
            continue
        goals_for = home["homeGoals"].sum() + away["awayGoals"].sum()
        goals_against = home["awayGoals"].sum() + away["homeGoals"].sum()
        attack[team] = (goals_for / games) / league_avg
        defense[team] = (goals_against / games) / league_avg

    return StrengthModel(
        attack=attack,
        defense=defense,
        league_home_avg=league_home_avg,
        league_away_avg=league_away_avg,
    )


def predict_match_probs(model, home, away):
    exp_home = model.league_home_avg * model.attack.get(home, 1.0) * model.defense.get(away, 1.0)
    exp_away = model.league_away_avg * model.attack.get(away, 1.0) * model.defense.get(home, 1.0)

    goals = np.arange(model.max_goals + 1)
    home_probs = poisson.pmf(goals, exp_home)
    away_probs = poisson.pmf(goals, exp_away)
    matrix = np.outer(home_probs, away_probs)

    p_home = np.tril(matrix, -1).sum()
    p_draw = np.trace(matrix)
    p_away = np.triu(matrix, 1).sum()

    total = p_home + p_draw + p_away
    if total <= 0:
        return 1 / 3, 1 / 3, 1 / 3
    return p_home / total, p_draw / total, p_away / total


def predict_fixtures(fixtures, model):
    rows = []
    for _, row in fixtures.iterrows():
        home = row["homeTeam"]
        away = row["awayTeam"]
        p_home, p_draw, p_away = predict_match_probs(model, home, away)
        rows.append(
            {
                "utcDate": row["utcDate"],
                "homeTeam": home,
                "awayTeam": away,
                "p_home_win": p_home,
                "p_draw": p_draw,
                "p_away_win": p_away,
            }
        )
    return pd.DataFrame(rows)
