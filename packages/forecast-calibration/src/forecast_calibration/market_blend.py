from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import logsumexp

from forecast_calibration.dataset import CALIBRATION_LEAGUES, dc_prefix
from forecast_calibration.fit import _balance, fit_weights
from standing_prediction.odds import _football_data_csv, _uk_dates
from standing_prediction.utils import normalize_team

LOG = logging.getLogger(__name__)
KEYS = ["league", "season", "utcDate", "homeTeam", "awayTeam"]
# No-odds pools; every other score compares with the current market blend.
MODEL_SCORES = ("current_model", "free_model", "free_model_bias")
# Same priority as the calibration dataset: average prices, then the older average, then Bet365.
SOURCES = ("Avg", "BbAv", "B365")
# football-data.co.uk warns its Pinnacle columns are unreliable from 23 July 2025.
PINNACLE_LAST_SEASON = 2024


def raw_quotes(league, season):
    raw = _football_data_csv(league, season, 30, ".cache/football-data-uk", True)
    dates = _uk_dates(raw)
    match_day = pd.to_datetime(dates.dt.tz_convert("Europe/London").dt.strftime("%Y-%m-%d"), utc=True)
    has_time = raw["Time"].astype(str).str.fullmatch(r"\d{1,2}:\d{2}", na=False) if "Time" in raw else pd.Series(False, index=raw.index)
    out = pd.DataFrame({"league": league, "season": season,
                        "utcDate": dates.where(has_time, match_day + pd.Timedelta(hours=12)).map(lambda t: t.isoformat() if pd.notna(t) else None),
                        "homeTeam": raw["HomeTeam"].map(normalize_team), "awayTeam": raw["AwayTeam"].map(normalize_team)})
    out[["odds_h", "odds_d", "odds_a"]] = np.nan
    out["raw_source"] = ""
    for prefix in SOURCES:
        columns = [f"{prefix}{c}" for c in "HDA"]
        if not set(columns).issubset(raw.columns):
            continue
        decimal = raw[columns].apply(pd.to_numeric, errors="coerce")
        valid = np.isfinite(decimal).all(axis=1) & decimal.gt(1).all(axis=1) & out["raw_source"].eq("")
        out.loc[valid, ["odds_h", "odds_d", "odds_a"]] = decimal.loc[valid].to_numpy(dtype=float)
        out.loc[valid, "raw_source"] = prefix
    pinnacle = np.full((len(raw), 3), np.nan)
    if "PSH" in raw and season <= PINNACLE_LAST_SEASON:
        prices = raw[[f"PS{c}" for c in "HDA"]].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(prices).all(axis=1) & (prices > 1).all(axis=1)
        pinnacle[valid] = prices[valid]
    out[["ps_h", "ps_d", "ps_a"]] = pinnacle
    return out.dropna(subset=["utcDate"])


# Margin removal: each maps inverse decimal odds to probabilities summing to one. Ranges also admit the rare
# provider row whose prices sum below one (a negative margin).
def _solve(function, low, high, iterations=200):
    # Vectorised bisection on a row-wise increasing function whose root makes probabilities sum to one.
    low, high = np.full(function.rows, low, dtype=float), np.full(function.rows, high, dtype=float)
    for _ in range(iterations):
        middle = (low + high) / 2
        above = function(middle) > 1
        low, high = np.where(above, low, middle), np.where(above, middle, high)
    return (low + high) / 2


class _Rows:
    def __init__(self, rows, total):
        self.rows, self.total = rows, total

    def __call__(self, parameter):
        return self.total(parameter[:, None]).sum(axis=1)


def proportional(inverse):
    return inverse / inverse.sum(axis=1, keepdims=True)


def additive(inverse):
    # Can go negative for long prices; such rows are clipped and renormalised and counted in the report.
    p = inverse - (inverse.sum(axis=1, keepdims=True) - 1) / inverse.shape[1]
    p = np.clip(p, 1e-6, None)
    return p / p.sum(axis=1, keepdims=True)


def power(inverse):
    # p_i = pi_i ** k; the sum falls as k rises, so solve on -k to keep the function increasing.
    k = -_solve(_Rows(len(inverse), lambda nk: inverse ** -nk), -20.0, -0.2)
    return inverse ** k[:, None]


def odds_ratio(inverse):
    # Cheung (2015): every outcome's odds ratio against the book is the same constant c >= 1.
    shape = lambda c: inverse / (c * (1 - inverse) + inverse)
    c = -_solve(_Rows(len(inverse), lambda nc: shape(-nc)), -50.0, -0.02)
    return shape(c[:, None])


def shin(inverse):
    # Shin (1993): z is the share of insider money; Jullien and Salanie's closed form for each z.
    total = inverse.sum(axis=1, keepdims=True)
    shape = lambda z: (np.sqrt(z ** 2 + 4 * (1 - z) * inverse ** 2 / total) - z) / (2 * (1 - z))
    z = -_solve(_Rows(len(inverse), lambda nz: shape(-nz)), -0.99, 0.5)
    return shape(z[:, None])


METHODS = {"proportional": proportional, "additive": additive, "power": power, "odds_ratio": odds_ratio, "shin": shin}


def attach_quotes(data):
    quotes = pd.concat([raw_quotes(league, season) for league, season in data[["league", "season"]].drop_duplicates().itertuples(index=False)])
    if quotes[KEYS].duplicated().any():
        raise ValueError("Duplicate raw quote keys.")
    joined = data.merge(quotes, on=KEYS, how="left", validate="one_to_one")
    has_book = joined["book_h"].notna()
    if (joined["raw_source"].fillna("") != joined["odds_source"].fillna("")).any():
        raise ValueError("Raw quote sources differ from the calibration dataset.")
    inverse = 1 / joined.loc[has_book, ["odds_h", "odds_d", "odds_a"]].to_numpy(dtype=float)
    # Proportional removal on the raw prices must reproduce the dataset's market probabilities.
    if not np.allclose(proportional(inverse), joined.loc[has_book, [f"book_{c}" for c in "hda"]].to_numpy(dtype=float), atol=1e-12):
        raise ValueError("Raw quotes do not reproduce the dataset's de-margined probabilities.")
    return joined


def demargined(joined, method, columns=("odds_h", "odds_d", "odds_a")):
    out = np.full((len(joined), 3), np.nan)
    present = joined[list(columns)].notna().all(axis=1).to_numpy()
    out[present] = METHODS[method](1 / joined.loc[present, list(columns)].to_numpy(dtype=float))
    if not np.allclose(out[present].sum(axis=1), 1, atol=1e-9) or (out[present] <= 0).any():
        raise ValueError(f"{method} did not produce probability triples.")
    return out


# Log-linear pools: logits[n, k] = sum_j theta_j * feature_j[n, k], scored by softmax log loss.
def _log(p):
    return np.log(np.clip(p, 1e-12, 1))


def features(frame, book, variant, prefix):
    dc = _log(frame[[f"{prefix}_{c}" for c in "hda"]].to_numpy(dtype=float))
    elo = _log(frame[[f"elo_{c}" for c in "hda"]].to_numpy(dtype=float))
    draw, away = np.zeros_like(dc), np.zeros_like(dc)
    draw[:, 1], away[:, 2] = 1, 1
    parts = {"dc": dc, "elo": elo, "book": None if book is None else _log(book), "draw": draw, "away": away}
    return np.stack([parts[name] for name in VARIANTS[variant]], axis=-1)


# Free coefficients: the weights need not sum to one, so a pool can sharpen or soften, and add outcome intercepts.
VARIANTS = {
    "free_model": ("dc", "elo"),
    "free_model_bias": ("dc", "elo", "draw", "away"),
    "book_scale": ("book",),
    "book_scale_bias": ("book", "draw", "away"),
    "free_market": ("dc", "elo", "book"),
    "free_market_bias": ("dc", "elo", "book", "draw", "away"),
}


def losses(logits, y):
    return logsumexp(logits, axis=1) - logits[np.arange(len(y)), y]


def fit_pool(x, y, weights, start):
    actual = np.eye(3)[y]

    def objective(theta):
        logits = x @ theta
        residual = np.exp(logits - logsumexp(logits, axis=1, keepdims=True)) - actual
        return float(weights @ losses(logits, y)), np.einsum("n,nk,nkj->j", weights, residual, x)

    fit = minimize(objective, start, jac=True, method="L-BFGS-B", options={"ftol": 1e-13, "gtol": 1e-9, "maxiter": 1000})
    # The loss is convex in theta; a line search can stop at machine precision with the gradient already flat.
    if np.abs(objective(fit.x)[1]).max() > 1e-6:
        raise RuntimeError(f"Pool optimisation failed: {fit.message}")
    return fit.x


def start_for(variant):
    defaults = {"dc": 0.85, "elo": 0.15, "book": 1.0, "draw": 0.0, "away": 0.0}
    names = VARIANTS[variant]
    if "book" in names:
        defaults.update(dc=0.0, elo=0.0)
    return np.array([defaults[name] for name in names])


def current_losses(train, test, book_test, xg_weight, xg_scale):
    # The production rule: refit the constrained geometric weights on the training seasons with fit.py.
    fitted = fit_weights(train, xg_weight, xg_scale)
    prefix = dc_prefix(xg_weight, xg_scale)
    dc = _log(test[[f"{prefix}_{c}" for c in "hda"]].to_numpy(dtype=float))
    elo = _log(test[[f"elo_{c}" for c in "hda"]].to_numpy(dtype=float))
    share = fitted["no_odds_weights"]["main"]
    model = share * dc + (1 - share) * elo
    y = test["y"].to_numpy(dtype=int)
    out = {"current_model": losses(model, y)}
    if book_test is not None:
        odds = fitted["weights"]["odds"]
        out["current_market"] = losses((1 - odds) * model + odds * _log(book_test), y)
    return out, fitted


def fold_losses(train, test, book_train, book_test, xg_weight, xg_scale):
    prefix = dc_prefix(xg_weight, xg_scale)
    train = train.copy()
    train[[f"book_{c}" for c in "hda"]] = book_train
    out, fitted = current_losses(train, test, book_test, xg_weight, xg_scale)
    out["book"] = losses(_log(book_test), test["y"].to_numpy(dtype=int))
    coefficients = {"current": {"odds": fitted["weights"]["odds"], "main_without_odds": fitted["no_odds_weights"]["main"]}}
    for variant, names in VARIANTS.items():
        uses_book = "book" in names
        x_train = features(train, book_train if uses_book else None, variant, prefix)
        theta = fit_pool(x_train, train["y"].to_numpy(dtype=int), _balance(train), start_for(variant))
        out[variant] = losses(features(test, book_test if uses_book else None, variant, prefix) @ theta, test["y"].to_numpy(dtype=int))
        coefficients[variant] = dict(zip(names, theta.tolist()))
    return out, coefficients


def summarise(frame, scores, baseline):
    # Equal league-season weights; SEs of differences cluster by league-season.
    clusters = frame["league"] + ":" + frame["season"].astype(str)
    means = pd.DataFrame(scores, index=frame.index).groupby(clusters).mean()
    rows = {}
    for name in means:
        difference = means[name] - means[baseline]
        rows[name] = {"log_loss": float(means[name].mean()), "minus_" + baseline: float(difference.mean()),
                      "se": float(difference.std(ddof=1) / np.sqrt(len(difference))) if len(difference) > 1 else None,
                      "seasons_better": int((difference < 0).sum()), "clusters": len(difference)}
    return rows


def split_summaries(frame, scores):
    return {"model": summarise(frame, {k: scores[k] for k in scores if k in MODEL_SCORES}, "current_model"),
            "market": summarise(frame, {k: scores[k] for k in scores if k not in MODEL_SCORES}, "current_market")}


def run(data, *, xg_weight, xg_scale, method, book_columns=("odds_h", "odds_d", "odds_a"), first_test=2017, holdout=(2024, 2025),
        per_match=None):
    book = demargined(data, method, book_columns)
    quoted = np.isfinite(book).all(axis=1)
    frame, book = data.loc[quoted].reset_index(drop=True), book[quoted]
    seasons = sorted(frame["season"].unique())
    designs = {"expanding": [([s for s in seasons if s < test], [test]) for test in seasons if test >= first_test],
               "chronological": [([s for s in seasons if s < min(holdout)], list(holdout))]}
    results = {}
    for design, folds in designs.items():
        pieces, coefficients = [], []
        for train_seasons, test_seasons in folds:
            train, test = frame["season"].isin(train_seasons).to_numpy(), frame["season"].isin(test_seasons).to_numpy()
            scores, fitted = fold_losses(frame[train].reset_index(drop=True), frame[test].reset_index(drop=True),
                                         book[train], book[test], xg_weight, xg_scale)
            pieces.append(pd.DataFrame(scores, index=np.flatnonzero(test)))
            coefficients.append({"train": train_seasons, "test": test_seasons, "coefficients": fitted})
        scores = pd.concat(pieces).sort_index()
        tested = frame.loc[scores.index]
        if per_match is not None:
            per_match[design] = pd.concat([tested[KEYS].reset_index(drop=True), scores.reset_index(drop=True)], axis=1)
        results[design] = {"matches": len(tested), **split_summaries(tested, scores), "folds": coefficients}
    return results


def external(calibration, outside, method, first_test=2017, per_match=None):
    # Pools fitted on the five calibration leagues' earlier seasons, scored on six leagues never used for fitting.
    # Both sides use the goals-only model, which is all the outside leagues have.
    book_in, book_out = demargined(calibration, method), demargined(outside, method)
    quoted_in, quoted_out = np.isfinite(book_in).all(axis=1), np.isfinite(book_out).all(axis=1)
    pieces = []
    for season in sorted(outside["season"].unique()):
        if season < first_test:
            continue
        train, test = quoted_in & (calibration["season"] < season).to_numpy(), quoted_out & (outside["season"] == season).to_numpy()
        scores, _ = fold_losses(calibration[train].reset_index(drop=True), outside[test].reset_index(drop=True),
                                book_in[train], book_out[test], 0.0, 1.0)
        pieces.append(pd.DataFrame(scores, index=np.flatnonzero(test)))
    scores = pd.concat(pieces).sort_index()
    tested = outside.loc[scores.index]
    if per_match is not None:
        per_match.update(pd.concat([tested[KEYS].reset_index(drop=True), scores.reset_index(drop=True)], axis=1).to_dict("series"))
    return {"matches": len(tested), **split_summaries(tested, scores)}


def gap_by_context(joined, xg_weight, xg_scale, share, method="power"):
    # Where the market beats the published no-odds blend at the artifact's weights; descriptive, equal league-season weights.
    prefix = dc_prefix(xg_weight, xg_scale)
    model = share * _log(joined[[f"{prefix}_{c}" for c in "hda"]].to_numpy(dtype=float)) + \
        (1 - share) * _log(joined[[f"elo_{c}" for c in "hda"]].to_numpy(dtype=float))
    book = demargined(joined, method)
    quoted = np.isfinite(book).all(axis=1)
    y = joined["y"].to_numpy(dtype=int)
    frame = joined.loc[quoted, ["league", "season", "homeTeam", "awayTeam", "forecast_at"]].copy()
    frame["gap"] = losses(model[quoted], y[quoted]) - losses(_log(book[quoted]), y[quoted])
    month = pd.to_datetime(frame["forecast_at"], utc=True).dt.month
    frame["phase"] = np.select([month.isin([7, 8, 9]), month.isin([10, 11, 12]), month.isin([1, 2, 3])],
                               ["Jul-Sep", "Oct-Dec", "Jan-Mar"], "Apr-Jun")
    # A club is promoted when it did not play in that league the previous season; 2015/16 has no earlier season here.
    teams = {(lg, s): set(g["homeTeam"]) for (lg, s), g in joined.groupby(["league", "season"])}
    promoted = [(row.homeTeam not in teams.get((row.league, row.season - 1), {row.homeTeam})) or
                (row.awayTeam not in teams.get((row.league, row.season - 1), {row.awayTeam})) for row in frame.itertuples()]
    frame["promoted"] = np.where(frame["season"].eq(frame["season"].min()), "unknown", np.where(promoted, "yes", "no"))
    out = {}
    for column in ("phase", "promoted", "league"):
        rows = {}
        for value, group in frame.groupby(column):
            means = group.groupby(["league", "season"])["gap"].mean()
            rows[str(value)] = {"matches": len(group), "gap": float(means.mean()),
                                "se": float(means.std(ddof=1) / np.sqrt(len(means))) if len(means) > 1 else None}
        out[column] = rows
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="R1/R2: log-linear market pools and margin removal on the saved calibration dataset.")
    parser.add_argument("--dataset", type=Path, default=Path("out/global-calibration/features/dataset.csv"))
    parser.add_argument("--robustness-dataset", type=Path, default=Path("out/global-calibration/robustness/dataset.csv"))
    parser.add_argument("--artifact", type=Path, default=Path("src/standing_prediction/calibrated_weights.json"))
    parser.add_argument("--out-dir", type=Path, default=Path("out/market-blend"))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    artifact = json.loads(args.artifact.read_text())
    digest = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    if digest != artifact["dataset"]["sha256"]:
        raise ValueError("Dataset hash differs from the calibration artifact.")
    data = pd.read_csv(args.dataset)
    data = data[data["league"].isin(CALIBRATION_LEAGUES)].reset_index(drop=True)
    joined = attach_quotes(data)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    xg_weight, xg_scale = artifact["xg_weight"], artifact["xg_scale"]
    report = {"dataset_sha256": digest, "artifact_version": artifact["version"], "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "xg_weight": xg_weight, "xg_scale": xg_scale,
              "matches": len(joined), "quoted": int(joined["book_h"].notna().sum()),
              "sources": joined["odds_source"].fillna("none").value_counts().to_dict(), "methods": {}}
    inverse = 1 / joined[["odds_h", "odds_d", "odds_a"]].dropna().to_numpy(dtype=float)
    report["additive_clipped"] = int((inverse - (inverse.sum(axis=1, keepdims=True) - 1) / 3 <= 1e-6).any(axis=1).sum())
    report["negative_margin_quotes"] = int((inverse.sum(axis=1) < 1).sum())
    report["overround"] = {"mean": float(inverse.sum(axis=1).mean() - 1), "median": float(np.median(inverse.sum(axis=1)) - 1)}
    for method in METHODS:
        LOG.info("Method %s.", method)
        per_match = {}
        report["methods"][method] = run(joined, xg_weight=xg_weight, xg_scale=xg_scale, method=method, per_match=per_match)
        for design, frame in per_match.items():
            frame.to_csv(args.out_dir / f"losses_{method}_{design}.csv", index=False)
    # Pinnacle pre-closing prices on the seasons where the provider trusts them, against the average on the same fixtures.
    pinnacle = joined[joined[["ps_h", "ps_d", "ps_a"]].notna().all(axis=1)].reset_index(drop=True)
    report["pinnacle"] = {"matches": len(pinnacle), "seasons": sorted(pinnacle["season"].unique().tolist()), "by_method": {}}
    for method in ("proportional", "power", "shin"):
        LOG.info("Pinnacle %s.", method)
        report["pinnacle"]["by_method"][method] = {
            "pinnacle": run(pinnacle, xg_weight=xg_weight, xg_scale=xg_scale, method=method, book_columns=("ps_h", "ps_d", "ps_a"), holdout=(2023, 2024)),
            "average_same_fixtures": run(pinnacle, xg_weight=xg_weight, xg_scale=xg_scale, method=method, holdout=(2023, 2024))}
    outside = pd.read_csv(args.robustness_dataset)
    if hashlib.sha256(args.robustness_dataset.read_bytes()).hexdigest() != artifact["robustness_dataset"]["sha256"]:
        raise ValueError("Robustness dataset hash differs from the calibration artifact.")
    outside = attach_quotes(outside)
    report["gap_by_context"] = gap_by_context(joined, xg_weight, xg_scale, artifact["no_odds_weights"]["main"])
    report["external"] = {}
    for method in ("proportional", "power", "shin"):
        LOG.info("External leagues %s.", method)
        per_match = {}
        report["external"][method] = external(joined, outside, method, per_match=per_match)
        pd.DataFrame(per_match).to_csv(args.out_dir / f"losses_{method}_external.csv", index=False)
    path = args.out_dir / "results.json"
    path.write_text(json.dumps(report, indent=2, default=float) + "\n")
    LOG.info("Wrote %s.", path)


if __name__ == "__main__":
    main()
