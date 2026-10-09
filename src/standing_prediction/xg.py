from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Dict

import numpy as np
import pandas as pd
import requests
from scipy.optimize import minimize

from standing_prediction.utils import cache_max_age, cached_get, normalize_team

UNDERSTAT_BASE = "https://understat.com"
XG_PROVIDER = "understat"
XG_COLUMNS = ["home_xg", "away_xg"]
# Understat covers these leagues from 2014/15 with post-match, penalty-inclusive shot xG.
COMPETITION_TO_UNDERSTAT_LEAGUE = {
    "PD": "La_liga", "PL": "EPL", "BL1": "Bundesliga", "SA": "Serie_A", "FL1": "Ligue_1",
}
UNDERSTAT_FIRST_SEASON = 2014


def fetch_understat_matches(*, competition, season, timeout=30, cache_dir=".cache/understat", use_cache=True):
    """Completed league matches with Understat xG; kickoff times are UTC."""
    league = COMPETITION_TO_UNDERSTAT_LEAGUE.get(competition)
    if league is None:
        raise ValueError(f"Understat does not cover competition {competition}.")
    if season < UNDERSTAT_FIRST_SEASON:
        raise ValueError(f"Understat xG starts in {UNDERSTAT_FIRST_SEASON}/{UNDERSTAT_FIRST_SEASON + 1 - 2000}.")
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"})
    content = cached_get(f"{UNDERSTAT_BASE}/getLeagueData/{league}/{season}", session=session, timeout=timeout,
                         cache_dir=cache_dir if use_cache else None, max_age=cache_max_age(season))
    rows = []
    for match in json.loads(content).get("dates", []):
        if not match.get("isResult"):
            continue
        rows.append({
            "understat_id": match["id"], "utcDate": match["datetime"],
            "homeTeam": match["h"]["title"], "awayTeam": match["a"]["title"],
            "homeGoals": match["goals"]["h"], "awayGoals": match["goals"]["a"],
            "home_xg": match["xG"]["h"], "away_xg": match["xG"]["a"],
        })
    columns = ["understat_id", "utcDate", "homeTeam", "awayTeam", "homeGoals", "awayGoals", *XG_COLUMNS]
    out = pd.DataFrame(rows, columns=columns)
    out["utcDate"] = pd.to_datetime(out["utcDate"], utc=True, errors="coerce")
    for column in ["homeGoals", "awayGoals", *XG_COLUMNS]:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    return out.sort_values("utcDate").reset_index(drop=True)


def attach_xg(matches, xg, *, max_kickoff_gap=pd.Timedelta(days=2)):
    """Join one season's xG onto its results by team pair, checking kickoff and final score.

    Rows that cannot be matched unambiguously keep missing xG; nothing is imputed.
    """
    out = matches.copy()
    for column in XG_COLUMNS:
        out[column] = np.nan
    coverage = {"provider": XG_PROVIDER, "finished": 0, "matched": 0, "unmatched": 0,
                "kickoff_mismatch": 0, "score_mismatch": 0}
    finished = out["homeGoals"].notna() & out["awayGoals"].notna()
    coverage["finished"] = int(finished.sum())
    if xg is None or xg.empty or not finished.any():
        coverage["unmatched"] = coverage["finished"]
        out.attrs["xg_coverage"] = coverage
        return out
    source = xg.assign(home_norm=xg["homeTeam"].map(normalize_team), away_norm=xg["awayTeam"].map(normalize_team))
    # Each home/away pairing occurs once per league season; duplicates make the join ambiguous.
    source = source.drop_duplicates(["home_norm", "away_norm"], keep=False).set_index(["home_norm", "away_norm"])
    kickoffs = pd.to_datetime(out["utcDate"], utc=True, errors="coerce")
    for index in out.index[finished]:
        key = (normalize_team(out.at[index, "homeTeam"]), normalize_team(out.at[index, "awayTeam"]))
        if key not in source.index:
            coverage["unmatched"] += 1
            continue
        row = source.loc[key]
        if pd.isna(kickoffs[index]) or abs(row["utcDate"] - kickoffs[index]) > max_kickoff_gap:
            coverage["kickoff_mismatch"] += 1
            continue
        if (row["homeGoals"], row["awayGoals"]) != (out.at[index, "homeGoals"], out.at[index, "awayGoals"]):
            coverage["score_mismatch"] += 1
            continue
        out.loc[index, XG_COLUMNS] = row[XG_COLUMNS].to_numpy(dtype=float)
        coverage["matched"] += 1
    out.attrs["xg_coverage"] = coverage
    return out


def load_season_xg(matches, *, competition, season, cache=True):
    """Attach Understat xG to one season's results; unavailable seasons keep missing xG."""
    try:
        xg = fetch_understat_matches(competition=competition, season=season, use_cache=cache)
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        out = attach_xg(matches, None)
        out.attrs["xg_coverage"]["error"] = type(exc).__name__
        return out
    return attach_xg(matches, xg)


@dataclass(frozen=True)
class XgStrengths:
    attack: Dict[str, float]
    defense: Dict[str, float]
    intercept: float
    home_advantage: float
    matches: int


def fit_xg_strengths(matches, *, reference_date=None, xi=0.003, lambda_reg=0.1, max_iter=2000):
    """Time-decayed attack/defense strengths fitted to xG with a quasi-Poisson log-link objective.

    Fractional xG is a continuous response, so only the Poisson mean structure is used, not
    an integer likelihood. Strengths are centered like the Dixon–Coles team parameters.
    """
    if not set(XG_COLUMNS).issubset(matches.columns):
        return None
    data = matches.dropna(subset=XG_COLUMNS).copy()
    data["utcDate"] = pd.to_datetime(data["utcDate"], utc=True)
    if reference_date is not None:
        reference_date = pd.to_datetime(reference_date, utc=True)
        data = data[data["utcDate"] < reference_date]
    if data.empty:
        return None
    latest = reference_date if reference_date is not None else data["utcDate"].max()
    teams = sorted(pd.unique(data[["homeTeam", "awayTeam"]].values.ravel("K")))
    if len(teams) < 2:
        return None
    index = {team: i for i, team in enumerate(teams)}
    n = len(teams)
    home = data["homeTeam"].map(index).to_numpy(dtype=int)
    away = data["awayTeam"].map(index).to_numpy(dtype=int)
    y_home = data["home_xg"].to_numpy(dtype=float)
    y_away = data["away_xg"].to_numpy(dtype=float)
    weights = np.exp(-xi * (latest - data["utcDate"]).dt.total_seconds().to_numpy() / 86400.0)

    def objective(params):
        intercept, home_adv, attack, defense = params[0], params[1], params[2:2 + n], params[2 + n:]
        log_home = intercept + home_adv + attack[home] + defense[away]
        log_away = intercept + attack[away] + defense[home]
        mu_home, mu_away = np.exp(np.clip(log_home, -15, 15)), np.exp(np.clip(log_away, -15, 15))
        loss = (weights * (mu_home - y_home * log_home + mu_away - y_away * log_away)).sum()
        loss += lambda_reg * (home_adv**2 + np.square(attack).sum() + np.square(defense).sum())
        r_home, r_away = weights * (mu_home - y_home), weights * (mu_away - y_away)
        grad = np.empty_like(params)
        grad[0] = r_home.sum() + r_away.sum()
        grad[1] = r_home.sum() + 2 * lambda_reg * home_adv
        grad[2:2 + n] = np.bincount(home, r_home, n) + np.bincount(away, r_away, n) + 2 * lambda_reg * attack
        grad[2 + n:] = np.bincount(away, r_home, n) + np.bincount(home, r_away, n) + 2 * lambda_reg * defense
        return float(loss), grad

    x0 = np.zeros(2 + 2 * n)
    x0[0] = np.log(max(np.average(y_away, weights=weights), 1e-3))
    result = minimize(objective, x0, jac=True, method="L-BFGS-B", options={"maxiter": max_iter})
    if not result.success:
        raise RuntimeError(f"xG strength fit failed: {result.message}")
    attack, defense = result.x[2:2 + n], result.x[2 + n:]
    shift_attack, shift_defense = attack.mean(), defense.mean()
    return XgStrengths(
        attack={team: float(attack[i] - shift_attack) for team, i in index.items()},
        defense={team: float(defense[i] - shift_defense) for team, i in index.items()},
        intercept=float(result.x[0] + shift_attack + shift_defense), home_advantage=float(result.x[1]),
        matches=len(data),
    )


def blend_xg_strengths(dc, xg, weight):
    """Blend log goal rates with xG-based rates through team strengths.

    Sharing the goal model's intercept and home advantage makes
    log(rate) = (1 - w) log(goal rate) + w log(xG rate) while keeping the goal scale, so
    provider differences in penalty or own-goal scope do not shift league scoring. Teams
    without xG history keep their goal-based strengths.
    """
    if xg is None or weight == 0:
        return dc
    if not 0 <= weight <= 1:
        raise ValueError("xG weight must be between 0 and 1.")
    attack, defense = dc.attack.copy(), dc.defense.copy()
    for team, i in dc.team_index.items():
        if team in xg.attack:
            attack[i] = (1 - weight) * attack[i] + weight * xg.attack[team]
            defense[i] = (1 - weight) * defense[i] + weight * xg.defense[team]
    return replace(dc, attack=attack, defense=defense)
