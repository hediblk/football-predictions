from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from standing_prediction.dixon_coles import fit_dixon_coles
from standing_prediction.utils import normalize_team

RESIDUAL_COLUMNS = ["utcDate", "home_key", "away_key", "goal_diff", "expected_diff", "residual"]


def encounter_residuals(results, *, refit_days=28, window_days=730, min_matches=200,
                        xi=0.003, lambda_reg=0.1, cache_dir=".cache/h2h"):
    """Each match's goal difference minus a prior-only Dixon–Coles expectation.

    The baseline for a match comes from a fit on the `window_days` before the start of its
    `refit_days` block, so it never uses that match or later results. Matches without
    `min_matches` earlier results in the window get no residual.
    """
    data = results.dropna(subset=["homeGoals", "awayGoals", "utcDate"]).copy()
    data["utcDate"] = pd.to_datetime(data["utcDate"], utc=True)
    data["home_key"] = data["homeTeam"].map(normalize_team)
    data["away_key"] = data["awayTeam"].map(normalize_team)
    data = data.drop_duplicates(["utcDate", "home_key", "away_key"]).sort_values("utcDate").reset_index(drop=True)
    if data.empty:
        return pd.DataFrame(columns=RESIDUAL_COLUMNS)
    cache_path = None
    if cache_dir is not None:
        fingerprint = data[["utcDate", "home_key", "away_key", "homeGoals", "awayGoals"]].to_csv(index=False)
        key = hashlib.sha256(f"{fingerprint}|{refit_days}|{window_days}|{min_matches}|{xi}|{lambda_reg}".encode()).hexdigest()
        cache_path = Path(cache_dir) / f"{key}.csv"
        if cache_path.exists():
            return pd.read_csv(cache_path, parse_dates=["utcDate"])
    fit_data = data.rename(columns={"homeTeam": "_home", "awayTeam": "_away", "home_key": "homeTeam", "away_key": "awayTeam"})
    rows = []
    start, end = data["utcDate"].min().normalize(), data["utcDate"].max()
    for block_start in pd.date_range(start, end + pd.Timedelta(days=refit_days), freq=f"{refit_days}D"):
        block_end = block_start + pd.Timedelta(days=refit_days)
        block = fit_data[(fit_data["utcDate"] >= block_start) & (fit_data["utcDate"] < block_end)]
        if block.empty:
            continue
        train = fit_data[(fit_data["utcDate"] < block_start) & (fit_data["utcDate"] >= block_start - pd.Timedelta(days=window_days))]
        if len(train) < min_matches:
            continue
        model = fit_dixon_coles(train, reference_date=block_start, xi=xi, lambda_reg=lambda_reg)
        for match in block.itertuples(index=False):
            home_rate, away_rate = model.expected_goals(match.homeTeam, match.awayTeam)
            rows.append({"utcDate": match.utcDate, "home_key": match.homeTeam, "away_key": match.awayTeam,
                         "goal_diff": match.homeGoals - match.awayGoals, "expected_diff": home_rate - away_rate})
    out = pd.DataFrame(rows, columns=RESIDUAL_COLUMNS[:-1])
    out["residual"] = out["goal_diff"] - out["expected_diff"]
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(cache_path, index=False)
    return out


def pair_effects(residuals, as_of, *, half_life_days=730, shrinkage=4.0):
    """Recency-weighted, shrunk mean residual for each pair, oriented first key minus second.

    Venues are pooled because each residual already accounts for home advantage.
    """
    as_of = pd.to_datetime(as_of, utc=True)
    data = residuals[pd.to_datetime(residuals["utcDate"], utc=True) < as_of].copy()
    columns = ["team_a", "team_b", "effect", "meetings", "weight", "effective_meetings"]
    if data.empty:
        return pd.DataFrame(columns=columns)
    age = (as_of - pd.to_datetime(data["utcDate"], utc=True)).dt.total_seconds() / 86400.0
    data["w"] = np.power(0.5, age / half_life_days)
    swap = data["home_key"] > data["away_key"]
    data["team_a"] = np.where(swap, data["away_key"], data["home_key"])
    data["team_b"] = np.where(swap, data["home_key"], data["away_key"])
    data["oriented"] = np.where(swap, -data["residual"], data["residual"])
    data["wr"] = data["w"] * data["oriented"]
    data["w2"] = data["w"] ** 2
    grouped = data.groupby(["team_a", "team_b"]).agg(
        meetings=("w", "size"), weight=("w", "sum"), wr=("wr", "sum"), w2=("w2", "sum")).reset_index()
    grouped["effect"] = grouped["wr"] / (shrinkage + grouped["weight"])
    grouped["effective_meetings"] = grouped["weight"] ** 2 / grouped["w2"]
    return grouped[columns]


def h2h_shifts(teams, effects, coefficient):
    """Log-rate shifts for every ordered pairing: +shift to the home rate, -shift to the away rate."""
    if coefficient == 0 or effects is None or effects.empty:
        return {}
    lookup = {(row.team_a, row.team_b): row.effect for row in effects.itertuples(index=False)}
    shifts = {}
    for home in teams:
        for away in teams:
            if home == away:
                continue
            a, b = normalize_team(home), normalize_team(away)
            effect = lookup.get((a, b), -lookup.get((b, a), 0.0))
            if effect:
                shifts[(home, away)] = coefficient * float(effect)
    return shifts
