from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln


@dataclass(frozen=True)
class DixonColesModel:
    teams: Tuple[str, ...]
    team_index: Dict[str, int]
    intercept: float
    home_advantage: float
    attack: np.ndarray
    defense: np.ndarray
    rho: float
    xi: float
    fitted_at: datetime

    def expected_goals(self, home, away):
        home_idx = self.team_index[home]
        away_idx = self.team_index[away]

        log_lambda = (
            self.intercept
            + self.home_advantage
            + float(self.attack[home_idx])
            + float(self.defense[away_idx])
        )
        log_mu = self.intercept + float(self.attack[away_idx]) + float(self.defense[home_idx])

        lambda_ = float(np.exp(np.clip(log_lambda, -15.0, 15.0)))
        mu_ = float(np.exp(np.clip(log_mu, -15.0, 15.0)))

        return lambda_, mu_

    def score_matrix(self, home, away, *, max_goals=10):
        lambda_, mu_ = self.expected_goals(home, away)
        goals = np.arange(max_goals + 1, dtype=int)

        home_p = _poisson_probs(goals, lambda_)
        away_p = _poisson_probs(goals, mu_)
        matrix = np.outer(home_p, away_p)

        # Dixon–Coles low-score correction (tau) affects only 0/1 goals combinations.
        tau = np.ones_like(matrix)
        rho = self.rho
        tau[0, 0] = max(0.0, 1.0 - (lambda_ * mu_ * rho))
        tau[0, 1] = max(0.0, 1.0 + (lambda_ * rho))
        tau[1, 0] = max(0.0, 1.0 + (mu_ * rho))
        tau[1, 1] = max(0.0, 1.0 - rho)

        matrix = matrix * tau
        total = float(matrix.sum())
        if total <= 0:
            # Fallback to independent Poisson if correction collapses mass.
            matrix = np.outer(home_p, away_p)
            total = float(matrix.sum())
        matrix = matrix / total
        return goals, matrix

    def match_outcome_probs(self, home, away, *, max_goals=10):
        goals, matrix = self.score_matrix(home, away, max_goals=max_goals)
        _ = goals  # unused, but returned to keep API symmetric.

        p_draw = float(np.trace(matrix))
        p_home = float(np.tril(matrix, -1).sum())
        p_away = float(np.triu(matrix, 1).sum())

        total = p_home + p_draw + p_away
        if total <= 0:
            return 1 / 3, 1 / 3, 1 / 3
        return p_home / total, p_draw / total, p_away / total


def fit_dixon_coles(
    matches,
    *,
    xi=0.003,
    lambda_reg=0.1,
    rho_bounds=(-0.2, 0.2),
    max_iter=2000,
):
    required = {"homeTeam", "awayTeam", "homeGoals", "awayGoals", "utcDate"}
    missing = required - set(matches.columns)
    if missing:
        raise ValueError(f"matches is missing required columns: {sorted(missing)}")

    finished = matches.dropna(subset=["homeGoals", "awayGoals"]).copy()
    if finished.empty:
        raise ValueError("No finished matches available to fit the model.")

    finished = finished.sort_values("utcDate")
    teams = tuple(pd.unique(finished[["homeTeam", "awayTeam"]].values.ravel("K")))
    team_index = {t: i for i, t in enumerate(teams)}
    n_teams = len(teams)
    if n_teams < 2:
        raise ValueError("Need at least two teams to fit the model.")

    ref_team = teams[0]
    ref_idx = team_index[ref_team]

    home_idx = finished["homeTeam"].map(team_index).to_numpy(dtype=int)
    away_idx = finished["awayTeam"].map(team_index).to_numpy(dtype=int)
    home_goals = finished["homeGoals"].to_numpy(dtype=int)
    away_goals = finished["awayGoals"].to_numpy(dtype=int)

    latest_date = pd.to_datetime(finished["utcDate"]).max()
    days_ago = (latest_date - pd.to_datetime(finished["utcDate"])).dt.days.to_numpy(dtype=float)
    weights = np.exp(-xi * days_ago)

    # Reasonable initial values
    mean_goals = float((home_goals.mean() + away_goals.mean()) / 2.0)
    intercept0 = float(np.log(max(mean_goals, 1e-3)))
    home_adv0 = float(np.log(max(home_goals.mean(), 1e-3)) - np.log(max(away_goals.mean(), 1e-3))) / 2.0

    # Parameter vector:
    # [intercept, home_adv, attack (n-1), defense (n-1), rho]
    x0 = np.zeros(2 + 2 * (n_teams - 1) + 1, dtype=float)
    x0[0] = intercept0
    x0[1] = home_adv0

    bounds = [(None, None), (None, None)]
    bounds += [(None, None)] * (n_teams - 1)  # attack
    bounds += [(None, None)] * (n_teams - 1)  # defense
    bounds += [rho_bounds]

    def unpack(params):
        intercept = float(params[0])
        home_adv = float(params[1])
        attack_free = params[2 : 2 + (n_teams - 1)]
        defense_free = params[2 + (n_teams - 1) : 2 + 2 * (n_teams - 1)]
        rho = float(params[-1])

        attack = np.zeros(n_teams, dtype=float)
        defense = np.zeros(n_teams, dtype=float)

        ai = 0
        di = 0
        for i in range(n_teams):
            if i == ref_idx:
                continue
            attack[i] = float(attack_free[ai])
            ai += 1
        for i in range(n_teams):
            if i == ref_idx:
                continue
            defense[i] = float(defense_free[di])
            di += 1

        return intercept, home_adv, attack, defense, rho

    def neg_log_likelihood(params):
        intercept, home_adv, attack, defense, rho = unpack(params)

        log_lambda = (
            intercept + home_adv + attack[home_idx] + defense[away_idx]
        )  # type: ignore[index]
        log_mu = intercept + attack[away_idx] + defense[home_idx]  # type: ignore[index]

        lambda_ = np.exp(np.clip(log_lambda, -15.0, 15.0))
        mu_ = np.exp(np.clip(log_mu, -15.0, 15.0))

        log_p_home = home_goals * np.log(lambda_) - lambda_ - gammaln(home_goals + 1)
        log_p_away = away_goals * np.log(mu_) - mu_ - gammaln(away_goals + 1)

        # Tau correction (only for low scores)
        tau = np.ones_like(lambda_)
        mask_00 = (home_goals == 0) & (away_goals == 0)
        mask_01 = (home_goals == 0) & (away_goals == 1)
        mask_10 = (home_goals == 1) & (away_goals == 0)
        mask_11 = (home_goals == 1) & (away_goals == 1)

        tau[mask_00] = 1.0 - (lambda_[mask_00] * mu_[mask_00] * rho)
        tau[mask_01] = 1.0 + (lambda_[mask_01] * rho)
        tau[mask_10] = 1.0 + (mu_[mask_10] * rho)
        tau[mask_11] = 1.0 - rho

        # Guard against log(<=0) from extreme parameters.
        tau = np.clip(tau, 1e-12, None)
        log_tau = np.log(tau)

        ll = (weights * (log_tau + log_p_home + log_p_away)).sum()

        reg = lambda_reg * (np.square(params[1:-1]).sum())  # exclude intercept + rho
        return float(-(ll - reg))

    result = minimize(
        neg_log_likelihood,
        x0=x0,
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": max_iter},
    )
    if not result.success:
        raise RuntimeError(f"Dixon–Coles fit failed: {result.message}")

    intercept, home_adv, attack, defense, rho = unpack(result.x)
    return DixonColesModel(
        teams=teams,
        team_index=team_index,
        intercept=intercept,
        home_advantage=home_adv,
        attack=attack,
        defense=defense,
        rho=rho,
        xi=xi,
        fitted_at=datetime.utcnow(),
    )


def _poisson_probs(goals, mean):
    # Stable Poisson PMF via log space; goals is small (<= ~10).
    mean = float(max(mean, 1e-9))
    log_p = goals * np.log(mean) - mean - gammaln(goals + 1)
    p = np.exp(log_p)
    total = float(p.sum())
    if total <= 0:
        return np.full_like(goals, 1.0 / len(goals), dtype=float)
    return p / total
