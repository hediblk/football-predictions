"""Per-fixture forecasts: outcome chances, expected goals and the likeliest scores.

A forecast uses the season simulation's scoreline law: the blended home/draw/away
probabilities, with the score drawn from the goal model's distribution within that
outcome. Played matches are forecast from a model fitted at 00:00 UTC on their match
day, so each one only uses results known before kickoff.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

TOP_SCORELINES = 4


def scoreline_distribution(matrix, p_outcome):
    """Rescale a home-by-away goal matrix so its home-win, draw and away-win mass equals `p_outcome`."""
    matrix = np.asarray(matrix, dtype=float)
    home, away = np.indices(matrix.shape)
    out = np.zeros_like(matrix)
    for mask, p in zip((home > away, home == away, home < away), p_outcome):
        mass = matrix[mask].sum()
        if mass <= 0 or not np.isfinite(mass):
            raise ValueError("The score model assigned no finite mass to an outcome.")
        out[mask] = matrix[mask] * (p / mass)
    return out / out.sum()


def describe_match(matrix, p_outcome, *, score=None, top=TOP_SCORELINES):
    """Outcome chances, expected goals, likeliest scorelines and goal markets for one fixture.

    With `score` (home, away goals), also the probability the model gave that exact score.
    """
    dist = scoreline_distribution(matrix, p_outcome)
    goals = np.arange(dist.shape[0])
    best = np.argsort(-dist, axis=None, kind="stable")[:top]
    p_home, p_draw, p_away = (float(p) for p in p_outcome)
    out = {
        "p_home": p_home, "p_draw": p_draw, "p_away": p_away,
        "exp_home_goals": float(dist.sum(axis=1) @ goals), "exp_away_goals": float(dist.sum(axis=0) @ goals),
        "btts": float(dist[1:, 1:].sum()),
        "over_2_5": float(dist[np.add.outer(goals, goals) >= 3].sum()),
        "scorelines": [[int(h), int(a), float(dist[h, a])] for h, a in zip(*np.unravel_index(best, dist.shape))],
    }
    if score is not None:
        hg, ag = (int(value) for value in score)
        out["p_score"] = float(dist[hg, ag]) if hg < dist.shape[0] and ag < dist.shape[1] else 0.0
    return out


def match_days(fixtures):
    """Forecast origins for played fixtures: 00:00 UTC on each kickoff's day."""
    return pd.to_datetime(fixtures["utcDate"], utc=True).dt.floor("D")


def forecast_played(played, fit, forecast):
    """Forecast each played fixture from a model fitted at 00:00 UTC on its match day.

    `fit(origin)` returns a model fitted only on results before `origin`, or None when
    there is nothing to fit. `forecast(model, fixtures, origin)` returns one forecast per
    fixture, in order. Returns forecasts keyed by the fixtures' index labels.
    """
    out = {}
    if played.empty:
        return out
    for origin, group in played.groupby(match_days(played), sort=True):
        model = fit(origin)
        if model is not None:
            out.update(zip(group.index, forecast(model, group, origin)))
    return out


def match_records(fixtures, forecasts, columns):
    """JSON-ready rows for every fixture, each with its forecast fields (missing values become None)."""
    rows = []
    for index, row in fixtures.iterrows():
        record = {column: _plain(row.get(column)) for column in columns if column in fixtures.columns}
        record.update(forecasts.get(index, {}))
        rows.append(record)
    return rows


def write_match_forecasts(path, records, metadata):
    payload = {**metadata, "matches": records}
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False, default=_plain) + "\n")


def _plain(value):
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.isoformat()
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return None if not math.isfinite(value) else float(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
