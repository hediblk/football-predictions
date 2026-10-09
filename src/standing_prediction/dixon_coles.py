from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Mapping, Tuple

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
    # Optional per-fixture log-rate shifts, e.g. a head-to-head effect: +shift home, -shift away.
    pair_shift: Mapping[Tuple[str, str], float] = field(default_factory=dict)

    def expected_goals(self, home, away):
        home_idx = self.team_index.get(home)
        away_idx = self.team_index.get(away)
        home_attack = float(self.attack[home_idx]) if home_idx is not None else 0.0
        home_defense = float(self.defense[home_idx]) if home_idx is not None else 0.0
        away_attack = float(self.attack[away_idx]) if away_idx is not None else 0.0
        away_defense = float(self.defense[away_idx]) if away_idx is not None else 0.0

        log_lambda = self.intercept + self.home_advantage + home_attack + away_defense
        log_mu = self.intercept + away_attack + home_defense
        shift = self.pair_shift.get((home, away), 0.0)
        log_lambda += shift
        log_mu -= shift

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
    teams=None,
    reference_date=None,
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

    finished["utcDate"] = pd.to_datetime(finished["utcDate"], utc=True)
    latest_date = (
        pd.to_datetime(reference_date, utc=True)
        if reference_date is not None
        else finished["utcDate"].max()
    )
    finished = finished[finished["utcDate"] <= latest_date].sort_values("utcDate")
    if finished.empty:
        raise ValueError("No finished matches available before reference_date.")

    observed_teams = tuple(
        sorted(pd.unique(finished[["homeTeam", "awayTeam"]].values.ravel("K")))
    )
    observed_index = {team: i for i, team in enumerate(observed_teams)}
    model_teams = tuple(dict.fromkeys([*(teams if teams is not None else ()), *observed_teams]))
    team_index = {team: i for i, team in enumerate(model_teams)}
    n_teams = len(observed_teams)
    if n_teams < 2:
        raise ValueError("Need at least two teams to fit the model.")

    home_idx = finished["homeTeam"].map(observed_index).to_numpy(dtype=int)
    away_idx = finished["awayTeam"].map(observed_index).to_numpy(dtype=int)
    home_goals = finished["homeGoals"].to_numpy(dtype=int)
    away_goals = finished["awayGoals"].to_numpy(dtype=int)

    days_ago = (latest_date - finished["utcDate"]).dt.total_seconds().to_numpy() / 86400.0
    weights = np.exp(-xi * days_ago)

    # Reasonable initial values
    intercept0 = float(np.log(max(away_goals.mean(), 1e-3)))
    home_adv0 = float(np.log(max(home_goals.mean(), 1e-3)) - intercept0)

    # The last team strength enforces a zero sum; all teams share the same penalty.
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

        attack = np.append(attack_free, -attack_free.sum())
        defense = np.append(defense_free, -defense_free.sum())

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

        reg = lambda_reg * (home_adv**2 + np.square(attack).sum() + np.square(defense).sum())
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
    model_attack = np.zeros(len(model_teams), dtype=float)
    model_defense = np.zeros(len(model_teams), dtype=float)
    observed_positions = [team_index[team] for team in observed_teams]
    model_attack[observed_positions] = attack
    model_defense[observed_positions] = defense
    return DixonColesModel(
        teams=model_teams,
        team_index=team_index,
        intercept=intercept,
        home_advantage=home_adv,
        attack=model_attack,
        defense=model_defense,
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
