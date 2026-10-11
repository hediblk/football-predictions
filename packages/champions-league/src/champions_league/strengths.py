from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln

from standing_prediction.defaults import DEFAULT_FIT, DEFAULT_XG_WEIGHT
from standing_prediction.dixon_coles import DixonColesModel
from standing_prediction.elo import EloModel
from standing_prediction.xg import fit_xg_strengths


EUROPEAN_COMPETITIONS = {"CL", "EL", "ECL", "UCL", "UEL", "UECL"}
RATE_BOUNDS = (0.08, 6.0)


class _BoundedDixonColes(DixonColesModel):
    def expected_goals(self, home, away):
        return tuple(float(np.clip(rate, *RATE_BOUNDS)) for rate in super().expected_goals(home, away))


@dataclass(frozen=True)
class JointStrengths:
    european: DixonColesModel
    neutral: DixonColesModel
    elo: EloModel
    metadata: dict

    def expected_goals(self, home, away, neutral=False):
        return (self.neutral if neutral else self.european).expected_goals(home, away)

    def score_matrix(self, home, away, *, max_goals=10, neutral=False):
        if max_goals < 1:
            raise ValueError("max_goals must be at least one.")
        return (self.neutral if neutral else self.european).score_matrix(home, away, max_goals=max_goals)

    def match_outcome_probs(self, home, away, *, max_goals=10, neutral=False):
        return (self.neutral if neutral else self.european).match_outcome_probs(home, away, max_goals=max_goals)

    def elo_probs(self, home, away, neutral=False):
        model = replace(self.elo, home_advantage=0.0) if neutral else self.elo
        return model.predict_probs(home, away)


def _joint_elo(data, teams, team_leagues, as_of):
    ratings, previous_season, draw_decay = {}, {}, []
    groups = {}
    for team in teams:
        groups.setdefault(team_leagues[team], []).append(team)

    def center(league):
        values = [ratings[team] for team in groups[league] if team in ratings]
        return float(np.mean(values)) if values else 1500.0

    def regress(league, date):
        season = date.year if league == "NOR" else date.year - (date.month < 7)
        previous = previous_season.get(league, season)
        if season > previous:
            league_center = center(league)
            for team in groups[league]:
                if team in ratings:
                    ratings[team] = league_center + 0.75 ** (season - previous) * (ratings[team] - league_center)
        previous_season[league] = season

    # Clubs enter only when first observed; their league centers contain earlier results only.
    model = EloModel(ratings=ratings)
    for row in data.itertuples(index=False):
        for team in (row.homeTeam, row.awayTeam):
            league = team_leagues[team]
            regress(league, row.utcDate)
            if team not in ratings:
                ratings[team] = center(league)
        home_advantage = 0.0 if row.neutral else model.home_advantage
        current = replace(model, home_advantage=home_advantage)
        p_home, p_draw, _ = current.predict_probs(row.homeTeam, row.awayTeam)
        actual = 1.0 if row.homeGoals > row.awayGoals else 0.5 if row.homeGoals == row.awayGoals else 0.0
        delta = model.k_factor * (actual - p_home - 0.5 * p_draw)
        diff = ratings[row.homeTeam] + home_advantage - ratings[row.awayTeam]
        draw_decay.append(np.exp(-abs(diff) / model.draw_scale))
        ratings[row.homeTeam] += delta
        ratings[row.awayTeam] -= delta

    for league in groups:
        regress(league, as_of)
    for team in teams:
        if team not in ratings:
            ratings[team] = center(team_leagues[team])
    draw_target = float(np.clip((data.homeGoals == data.awayGoals).mean(), 0.05, 0.35))
    lower, upper = 0.0, 1.0
    decay = np.array(draw_decay)
    while np.clip(upper * decay, 0.05, 0.35).mean() < draw_target and upper < 1e6:
        upper *= 2
    for _ in range(40):
        midpoint = (lower + upper) / 2
        if np.clip(midpoint * decay, 0.05, 0.35).mean() < draw_target:
            lower = midpoint
        else:
            upper = midpoint
    return replace(model, draw_base=(lower + upper) / 2)


def _graph_audit(data, leagues, weights):
    neighbors = {league: set() for league in leagues}
    counts = dict.fromkeys(leagues, 0)
    effective = dict.fromkeys(leagues, 0.0)
    cross = data.homeLeague.to_numpy() != data.awayLeague.to_numpy()
    for home, away, weight in zip(data.loc[cross, "homeLeague"], data.loc[cross, "awayLeague"], weights[cross]):
        neighbors[home].add(away)
        neighbors[away].add(home)
        counts[home] += 1
        counts[away] += 1
        effective[home] += float(weight)
        effective[away] += float(weight)
    remaining, components = set(leagues), []
    while remaining:
        component, pending = set(), [min(remaining)]
        while pending:
            league = pending.pop()
            if league not in component:
                component.add(league)
                pending.extend(neighbors[league] - component)
        components.append(sorted(component))
        remaining -= component
    return {
        "components": components,
        "connected": len(components) == 1,
        "european_matches": counts,
        "effective_european_matches": effective,
        "sparse_leagues": [league for league in leagues if effective[league] < 10],
    }


def fit_strengths(
    history,
    *,
    teams,
    team_leagues,
    as_of,
    xi=DEFAULT_FIT["xi"],
    lambda_reg=DEFAULT_FIT["lambda_reg"],
    xg_weight=DEFAULT_XG_WEIGHT,
    league_offsets=True,
    offset_ridge=4.0,
):
    required = {"utcDate", "homeTeam", "awayTeam", "homeGoals", "awayGoals", "competition"}
    if missing := required - set(history.columns):
        raise ValueError(f"History is missing columns: {sorted(missing)}")
    if (not np.isfinite([xg_weight, xi, lambda_reg, offset_ridge]).all()
            or not 0 <= xg_weight <= 1 or xi < 0 or lambda_reg <= 0 or offset_ridge <= 0):
        raise ValueError("Invalid strength-model decay, regularization or xG weight.")
    origin = pd.to_datetime(as_of, utc=True)
    if pd.isna(origin):
        raise ValueError("as_of must be a valid forecast timestamp.")
    teams = tuple(teams)
    data = history.dropna(subset=["homeGoals", "awayGoals"]).copy()
    data["utcDate"] = pd.to_datetime(data.utcDate, utc=True)
    eligible = data.utcDate < origin
    if "available_at" in data:
        eligible &= pd.to_datetime(data.available_at, utc=True, errors="coerce") < origin
    data = data.loc[eligible].sort_values("utcDate", kind="stable").reset_index(drop=True)
    if data.empty:
        raise ValueError("No finished matches available strictly before as_of.")
    model_teams = tuple(sorted(set(teams) | set(data.homeTeam) | set(data.awayTeam)))
    if missing := set(model_teams) - set(team_leagues):
        raise ValueError(f"Missing domestic-league identities for teams: {sorted(missing)}")
    for side in ("home", "away"):
        mapped = data[f"{side}Team"].map(team_leagues)
        column = f"{side}League"
        if column in data and (data[column].notna() & data[column].ne(mapped)).any():
            raise ValueError(f"History has inconsistent {column} identities.")
        data[column] = mapped
    data["neutral"] = data.get("neutral", pd.Series(False, index=data.index)).fillna(False).astype(bool)
    goals = data[["homeGoals", "awayGoals"]].to_numpy(dtype=float)
    if not np.isfinite(goals).all() or (goals < 0).any() or not np.equal(goals, np.floor(goals)).all():
        raise ValueError("Strength fitting requires nonnegative integer 90-minute goals.")

    index = {team: i for i, team in enumerate(model_teams)}
    leagues = tuple(sorted({team_leagues[team] for team in model_teams}))
    league_index = {league: i for i, league in enumerate(leagues)}
    n, k = len(model_teams), len(leagues)
    team_group = np.array([league_index[team_leagues[team]] for team in model_teams])
    observed_teams = set(data.homeTeam) | set(data.awayTeam)
    observed_mask = np.array([team in observed_teams for team in model_teams])
    group_sizes = np.maximum(np.bincount(team_group[observed_mask], minlength=k), 1)
    home = data.homeTeam.map(index).to_numpy(dtype=int)
    away = data.awayTeam.map(index).to_numpy(dtype=int)
    home_league, away_league = team_group[home], team_group[away]
    european = (data.competition.isin(EUROPEAN_COMPETITIONS) | data.homeLeague.ne(data.awayLeague)).to_numpy()
    baseline = european.astype(int)
    venue = (~data.neutral).to_numpy(dtype=float)
    weights = np.exp(-xi * (origin - data.utcDate).dt.total_seconds().to_numpy() / 86400)
    graph = _graph_audit(data, leagues, weights)
    # A well-observed reference gives the other offsets a stable interpretation.
    reference = league_index[max(leagues, key=lambda league: graph["effective_european_matches"][league])]
    free_offsets = np.array([i for i in range(k) if i != reference], dtype=int) if league_offsets else np.array([], dtype=int)
    offset_penalty = np.array([offset_ridge * max(1.0, 10 / max(graph["effective_european_matches"][league], 1)) for league in leagues])
    log_factorials = gammaln(goals + 1).sum(axis=1)
    low = [(goals[:, 0] == h) & (goals[:, 1] == a) for h, a in ((0, 0), (0, 1), (1, 0), (1, 1))]
    log_min, log_max = np.log(RATE_BOUNDS)

    def center(values):
        means = np.bincount(team_group[observed_mask], weights=values[observed_mask], minlength=k) / group_sizes
        return np.where(observed_mask, values - means[team_group], 0.0)

    def unpack(params):
        attack = center(params[4:4 + n])
        defense = center(params[4 + n:4 + 2 * n])
        offsets = np.zeros(k)
        offsets[free_offsets] = params[4 + 2 * n:-1]
        return params[:2], params[2:4], attack, defense, offsets, params[-1]

    def objective(params):
        intercept, home_advantage, attack, defense, offsets, rho = unpack(params)
        contrast = offsets[home_league] - offsets[away_league]
        log_home = intercept[baseline] + home_advantage[baseline] * venue + attack[home] + defense[away] + contrast
        log_away = intercept[baseline] + attack[away] + defense[home] - contrast
        mu_home, mu_away = np.exp(np.clip(log_home, log_min, log_max)), np.exp(np.clip(log_away, log_min, log_max))
        tau = np.ones(len(data))
        tau[low[0]] = 1 - mu_home[low[0]] * mu_away[low[0]] * rho
        tau[low[1]] = 1 + mu_home[low[1]] * rho
        tau[low[2]] = 1 + mu_away[low[2]] * rho
        tau[low[3]] = 1 - rho
        active = tau > 1e-10
        safe_tau = np.maximum(tau, 1e-10)
        log_poisson = goals[:, 0] * np.log(mu_home) - mu_home + goals[:, 1] * np.log(mu_away) - mu_away - log_factorials
        loss = -np.dot(weights, log_poisson + np.log(safe_tau))
        loss += lambda_reg * (np.square(params[4:4 + 2 * n]).sum() + np.square(home_advantage).sum())
        loss += np.dot(offset_penalty, np.square(offsets))
        tau_home, tau_away, tau_rho = np.zeros((3, len(data)))
        tau_home[low[0]] = tau_away[low[0]] = -mu_home[low[0]] * mu_away[low[0]] * rho
        tau_home[low[1]] = mu_home[low[1]] * rho
        tau_away[low[2]] = mu_away[low[2]] * rho
        tau_rho[low[0]] = -mu_home[low[0]] * mu_away[low[0]]
        tau_rho[low[1]] = mu_home[low[1]]
        tau_rho[low[2]] = mu_away[low[2]]
        tau_rho[low[3]] = -1
        correction = weights * active / safe_tau
        r_home = (weights * (mu_home - goals[:, 0]) - correction * tau_home) * ((log_home > log_min) & (log_home < log_max))
        r_away = (weights * (mu_away - goals[:, 1]) - correction * tau_away) * ((log_away > log_min) & (log_away < log_max))
        grad_attack = np.bincount(home, r_home, minlength=n) + np.bincount(away, r_away, minlength=n)
        grad_defense = np.bincount(away, r_home, minlength=n) + np.bincount(home, r_away, minlength=n)
        grad_offsets = np.bincount(home_league, r_home - r_away, minlength=k) + np.bincount(away_league, r_away - r_home, minlength=k)
        gradient = np.concatenate([
            np.bincount(baseline, r_home + r_away, minlength=2),
            np.bincount(baseline, r_home * venue, minlength=2) + 2 * lambda_reg * home_advantage,
            center(grad_attack) + 2 * lambda_reg * params[4:4 + n],
            center(grad_defense) + 2 * lambda_reg * params[4 + n:4 + 2 * n],
            (grad_offsets + 2 * offset_penalty * offsets)[free_offsets],
            [-np.dot(correction, tau_rho)],
        ])
        return float(loss), gradient

    initial = np.zeros(5 + 2 * n + len(free_offsets))
    for category in (0, 1):
        selected = baseline == category
        if not selected.any():
            selected = np.ones(len(data), dtype=bool)
        mean_home, mean_away = np.average(goals[selected], axis=0, weights=weights[selected])
        initial[category] = np.log(max(mean_away, 0.3))
        initial[2 + category] = np.clip(np.log(max(mean_home, 0.3)) - initial[category], -0.2, 0.6)
    bounds = [(np.log(0.3), np.log(3))] * 2 + [(-0.2, 0.6)] * 2
    bounds += [(-1.5, 1.5)] * (2 * n) + [(-1.2, 1.2)] * len(free_offsets) + [(-0.15, 0.15)]
    result = minimize(objective, initial, jac=True, method="L-BFGS-B", bounds=bounds, options={"maxiter": 2000, "ftol": 1e-9})
    if not result.success or not np.isfinite(result.fun):
        raise RuntimeError(f"Joint European strength fit failed: {result.message}")
    intercept, home_advantage, attack, defense, offsets, rho = unpack(result.x)
    xg_metadata = {"weight": float(xg_weight), "matches": 0, "teams": 0, "leagues": {}}
    if xg_weight and {"home_xg", "away_xg"}.issubset(data.columns):
        for league in leagues:
            domestic = data.loc[~european & data.homeLeague.eq(league)]
            if domestic.empty:
                continue
            xg = fit_xg_strengths(domestic, reference_date=origin, xi=xi, lambda_reg=lambda_reg)
            if xg is None:
                continue
            observed = [team for team in model_teams if team_leagues[team] == league and team in xg.attack]
            positions = np.array([index[team] for team in observed])
            # Center the adjustment over observed clubs so missing xG keeps its goal strengths.
            for values, estimates in ((attack, xg.attack), (defense, xg.defense)):
                adjustment = np.array([estimates[team] for team in observed]) - values[positions]
                values[positions] += xg_weight * (adjustment - adjustment.mean())
            xg_metadata["leagues"][league] = {"matches": xg.matches, "teams": len(observed)}
            xg_metadata["matches"] += xg.matches
            xg_metadata["teams"] += len(observed)

    domestic_teams = set(data.loc[~european, ["homeTeam", "awayTeam"]].to_numpy().ravel())
    common = _BoundedDixonColes(
        teams=model_teams, team_index=index, intercept=float(intercept[1]), home_advantage=float(home_advantage[1]),
        attack=attack + offsets[team_group], defense=defense - offsets[team_group], rho=float(rho), xi=float(xi),
        fitted_at=datetime.now(timezone.utc),
    )
    field_rates = [rate for home in teams for away in teams if home != away
                   for rate in DixonColesModel.expected_goals(common, home, away)]
    guarded_rates = sum(rate < RATE_BOUNDS[0] or rate > RATE_BOUNDS[1] for rate in field_rates)
    metadata = {
        "model": "joint-european-dixon-coles", "as_of": origin.isoformat(), "matches": len(data),
        "domestic_matches": int((~european).sum()), "european_matches": int(european.sum()),
        "latest_result": data.utcDate.max().isoformat(), "xi": float(xi), "lambda_reg": float(lambda_reg),
        "league_offsets_enabled": bool(league_offsets), "offset_ridge": float(offset_ridge),
        "reference_league": leagues[reference], "league_offsets": {league: float(offsets[i]) for i, league in enumerate(leagues)},
        "graph": graph, "xg": xg_metadata, "goal_rate_bounds": list(RATE_BOUNDS),
        "guarded_field_rates": int(guarded_rates), "field_rates_evaluated": len(field_rates),
        "raw_field_rate_range": [min(field_rates), max(field_rates)] if field_rates else [],
        "domestic_baseline": {"intercept": float(intercept[0]), "home_advantage": float(home_advantage[0])},
        "european_baseline": {"intercept": float(intercept[1]), "home_advantage": float(home_advantage[1]), "rho": float(rho)},
        "teams_without_domestic_history": sorted(set(teams) - domestic_teams),
        "teams_without_any_history": sorted(set(teams) - observed_teams),
        "optimizer": {"success": bool(result.success), "iterations": int(result.nit), "objective": float(result.fun)},
        "elo": {"initial_rating": 1500, "season_regression": 0.75, "new_clubs": "earlier league center", "neutral_home_advantage": 0},
        "uncertainty": "Conditional fitted strengths; sparse or disconnected country offsets are regularized priors, not precise estimates.",
    }
    return JointStrengths(common, replace(common, home_advantage=0.0), _joint_elo(data, model_teams, team_leagues, origin), metadata)
