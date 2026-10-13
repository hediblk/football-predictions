"""Club strength ratings from a fitted goal model, on a points-share scale."""

from __future__ import annotations

import numpy as np
import pandas as pd

from standing_prediction.dixon_coles import score_matrix_from_rates


def points_share(attack, defense, opponent_attack, opponent_defense, *, intercept, rho, home_advantage=0.0, max_goals=10):
    """Expected share of the points (0-100) a club takes off one opponent.

    Strengths are Dixon–Coles log-rate parameters (a lower defence concedes less). A positive
    `home_advantage` hosts the club, a negative one hosts the opponent.
    """
    host, visit = max(home_advantage, 0.0), max(-home_advantage, 0.0)
    rates = np.exp(np.clip([intercept + host + attack + opponent_defense,
                            intercept + visit + opponent_attack + defense], -15.0, 15.0))
    _, matrix = score_matrix_from_rates(*rates, rho, max_goals=max_goals)
    home, away = np.indices(matrix.shape)
    return float(100 * (3 * matrix[home > away].sum() + matrix[home == away].sum()) / 3)


def club_ratings(dc, teams, reference=None):
    """Ratings for `teams` against the average of `reference` clubs (default: `teams` themselves).

    A rating is the share of points a club would take off the average club on a neutral pitch.
    The attack rating rates the club as if its defence were as far above average as its attack,
    and the defence rating the reverse, so all three share one scale. Home and away ratings host
    the club or its opponent with the model's home advantage. Goals are per game against the
    average club on a neutral pitch.
    """
    index = [dc.team_index[team] for team in teams]
    attack, defense = dc.attack[index], dc.defense[index]
    pool = index if reference is None else [dc.team_index[team] for team in reference]
    mean_attack, mean_defense = float(dc.attack[pool].mean()), float(dc.defense[pool].mean())

    def share(a, d, venue=0.0):
        return points_share(a, d, mean_attack, mean_defense, intercept=dc.intercept, rho=dc.rho, home_advantage=venue)

    rows = []
    for team, a, d in zip(teams, attack, defense):
        rows.append({
            "team": team,
            "rating": share(a, d),
            "attack_rating": share(a, mean_defense - (a - mean_attack)),
            "defense_rating": share(mean_attack + (mean_defense - d), d),
            "home_rating": share(a, d, dc.home_advantage),
            "away_rating": share(a, d, -dc.home_advantage),
            "goals_for": float(np.exp(dc.intercept + a + mean_defense)),
            "goals_against": float(np.exp(dc.intercept + mean_attack + d)),
            "attack": float(a), "defense": float(d),
        })
    return pd.DataFrame(rows).sort_values("rating", ascending=False, kind="stable").reset_index(drop=True)
