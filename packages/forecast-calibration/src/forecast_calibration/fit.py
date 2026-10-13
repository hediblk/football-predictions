from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import logsumexp

from forecast_calibration.dataset import dc_prefix

LEGACY_WEIGHTS = {"main": 0.35, "odds": 0.55, "elo": 0.10}


def _balance(frame):
    counts = frame.groupby(["league", "season"])["y"].transform("size").to_numpy(dtype=float)
    weights = 1 / counts
    return weights / weights.sum()


def _inputs(frame, xg_weight, xg_scale=1.0):
    arrays = [frame[[f"{prefix}_{c}" for c in "hda"]].to_numpy(dtype=float)
              for prefix in (dc_prefix(xg_weight, xg_scale), "elo", "book")]
    for probabilities in arrays[:2]:
        if not np.isfinite(probabilities).all() or (probabilities < 0).any() or not np.allclose(probabilities.sum(axis=1), 1):
            raise ValueError("Model probabilities must be finite, nonnegative and sum to one.")
    available = np.isfinite(arrays[2]).all(axis=1)
    if ((arrays[2][available] <= 0).any() or not np.allclose(arrays[2][available].sum(axis=1), 1)
            or (np.isfinite(arrays[2]).any(axis=1) & ~available).any()):
        raise ValueError("Odds must be complete positive probability triples, or entirely missing.")
    return *(np.log(np.clip(p, 1e-12, 1)) for p in arrays), available


def _loss(logits, outcomes, weights):
    return float(weights @ (logsumexp(logits, axis=1) - logits[np.arange(len(outcomes)), outcomes]))


def score(frame, xg_weight, weights, xg_scale=1.0):
    dc, elo, book, available = _inputs(frame, xg_weight, xg_scale)
    y = frame["y"].to_numpy(dtype=int)
    balance = _balance(frame)
    main_share = weights["main"] / (weights["main"] + weights["elo"])
    model = main_share * dc + (1 - main_share) * elo
    no_odds = _loss(model, y, balance)
    result = {"matches": len(frame), "odds_matches": int(available.sum()), "no_odds_log_loss": no_odds,
              "dc_log_loss": _loss(dc, y, balance), "elo_log_loss": _loss(elo, y, balance)}
    if available.any():
        odds_balance = _balance(frame.loc[available])
        market = (1 - weights["odds"]) * model[available] + weights["odds"] * book[available]
        with_odds = _loss(market, y[available], odds_balance)
        result.update({"with_odds_log_loss": with_odds, "book_log_loss": _loss(book[available], y[available], odds_balance),
                       "objective": (no_odds + with_odds) / 2})
    else:
        result["objective"] = no_odds
    return result


def fit_weights(frame, xg_weight, xg_scale=1.0):
    dc, elo, book, available = _inputs(frame, xg_weight, xg_scale)
    y = frame["y"].to_numpy(dtype=int)
    balance = _balance(frame)
    difference = dc - elo
    odds_balance = _balance(frame.loc[available]) if available.any() else None
    actual = np.eye(3)[y]

    def objective(params):
        odds_share, main_share = params
        model = elo + main_share * difference
        residual = np.exp(model - logsumexp(model, axis=1, keepdims=True)) - actual
        loss = _loss(model, y, balance)
        gradient = np.array([0.0, balance @ (residual * difference).sum(axis=1)])
        if available.any():
            market_difference = book[available] - model[available]
            market = model[available] + odds_share * market_difference
            residual = np.exp(market - logsumexp(market, axis=1, keepdims=True)) - actual[available]
            loss = (loss + _loss(market, y[available], odds_balance)) / 2
            gradient += [odds_balance @ (residual * market_difference).sum(axis=1),
                         odds_balance @ (residual * ((1 - odds_share) * difference[available])).sum(axis=1)]
            gradient /= 2
        return loss, gradient

    fits = [minimize(objective, [q, 0.75], jac=True, method="L-BFGS-B",
                     bounds=[(0, 1 - 1e-6), (0, 1)], options={"ftol": 1e-12, "gtol": 1e-8}) for q in (0.0, 0.55, 0.9)]
    successful = [fit for fit in fits if fit.success]
    if not successful:
        raise RuntimeError(f"Weight optimization failed: {fits[0].message}")
    best = min(successful, key=lambda fit: fit.fun)
    odds_share, main_share = best.x
    if not available.any():
        odds_share = 0.0
    weights = {"main": float((1 - odds_share) * main_share), "odds": float(odds_share),
               "elo": float((1 - odds_share) * (1 - main_share))}
    return {"xg_weight": float(xg_weight), "xg_scale": float(xg_scale), "weights": weights,
            "no_odds_weights": {"main": float(main_share), "elo": float(1 - main_share)},
            "metrics": score(frame, xg_weight, weights, xg_scale)}


def select_weights(frame, xg_grid, xg_scale_grid=(1.0,)):
    candidates = [fit_weights(frame, w, scale) for w in xg_grid for scale in (xg_scale_grid if w else [1.0])]
    best = min(candidates, key=lambda c: (c["metrics"]["objective"], c["xg_weight"], abs(c["xg_scale"] - 1)))
    return best, candidates


def _evaluate(frame, fitted):
    return {"fitted": score(frame, fitted["xg_weight"], fitted["weights"], fitted["xg_scale"]),
            "baseline": score(frame, 0, LEGACY_WEIGHTS)}


def calibrate(frame, metadata, *, robustness=None, robustness_metadata=None, holdout_seasons=2):
    seasons = sorted(frame["season"].unique().tolist())
    leagues = sorted(frame["league"].unique().tolist())
    if frame.empty or len(seasons) <= holdout_seasons or holdout_seasons < 1 or len(leagues) < 2:
        raise ValueError("Calibration needs multiple leagues and more seasons than the chronological holdout.")
    if frame[["league", "season", "utcDate", "homeTeam", "awayTeam"]].duplicated().any():
        raise ValueError("Calibration contains duplicate matches.")
    if frame["y"].isna().any() or not frame["y"].isin([0, 1, 2]).all():
        raise ValueError("Outcomes must be 0 (home), 1 (draw), or 2 (away).")
    origins = pd.to_datetime(frame["forecast_at"], utc=True)
    if (pd.to_datetime(frame["training_last_available_at"], utc=True) > origins).any():
        raise ValueError("Training results extend past a forecast origin.")
    xg_grid = metadata["xg_grid"]
    xg_scale_grid = metadata.get("xg_scale_grid", [1.0])
    if 0 not in xg_grid or not frame["book_h"].notna().any():
        raise ValueError("Calibration needs the xG=0 baseline and historical odds.")
    held_out = seasons[-holdout_seasons:]
    earlier = frame[~frame["season"].isin(held_out)]
    frozen, _ = select_weights(earlier, xg_grid, xg_scale_grid)
    chronological = {"training_seasons": seasons[:-holdout_seasons], "held_out_seasons": held_out,
                     **frozen, "evaluation": _evaluate(frame[frame["season"].isin(held_out)], frozen)}
    folds = []
    # These leave-out folds measure stability; chronological holdout above measures future transfer.
    for column, values in (("season", seasons), ("league", leagues)):
        for value in values:
            fitted, _ = select_weights(frame[frame[column] != value], xg_grid, xg_scale_grid)
            folds.append({"held_out": column, "value": value, **fitted,
                          "evaluation": _evaluate(frame[frame[column] == value], fitted)})
    fitted, grid = select_weights(frame, xg_grid, xg_scale_grid)
    spread = {key: {"min": min(f["weights"][key] for f in folds), "max": max(f["weights"][key] for f in folds)}
              for key in fitted["weights"]}
    spread["main_without_odds"] = {"min": min(f["no_odds_weights"]["main"] for f in folds),
                                   "max": max(f["no_odds_weights"]["main"] for f in folds)}
    spread["xg_weight"] = {"min": min(f["xg_weight"] for f in folds), "max": max(f["xg_weight"] for f in folds)}
    spread["xg_scale"] = {"min": min(f["xg_scale"] for f in folds), "max": max(f["xg_scale"] for f in folds)}
    report = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(), **fitted,
              "h2h_weight": 0.0, "fit_settings": {key: metadata[key] for key in ("xi", "lambda_reg", "prior_seasons")},
              "dataset": metadata, "grid": grid, "chronological_holdout": chronological,
              "folds": folds, "fold_weight_spread": spread,
              "baseline": score(frame, 0, LEGACY_WEIGHTS),
              "objective": "Equal league-season weights; half log loss without odds, half with pre-closing odds. Missing-odds weights renormalize over main/Elo.",
              "odds_weight_limit": "At most 1 - 1e-6, keeping a defined main/Elo ratio when quotes are absent.",
              "limitations": ["Historical quote collection times are approximate; xG publication times are assumed.",
                              "Leave-out folds measure stability, not prospective performance; the latest seasons form a separate chronological holdout.",
                              "Weights are fixed after this explicit rerun; match-level tuning does not guarantee optimal long-horizon standings."]}
    if robustness is not None:
        outside = sorted(robustness["league"].unique().tolist())
        if set(outside) & set(leagues):
            raise ValueError("Robustness leagues must be excluded from fitting.")
        report["robustness"] = {league: _evaluate(robustness[robustness["league"] == league], fitted) for league in outside}
        report["robustness_dataset"] = robustness_metadata
    try:
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        revision = None
    report["code_version"] = {"git_revision": revision, "feature_sha256": metadata["feature_code_sha256"],
                              "optimizer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    signature = json.dumps({key: value for key, value in report.items() if key != "created_at"}, sort_keys=True).encode()
    report["version"] = f"global-{hashlib.sha256(signature).hexdigest()[:12]}"
    return report
