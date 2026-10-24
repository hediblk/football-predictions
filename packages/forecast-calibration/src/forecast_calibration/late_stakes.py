from __future__ import annotations

import argparse
import hashlib
import json
import logging
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import logsumexp

from forecast_calibration.dataset import CALIBRATION_LEAGUES, XG_COMPETITIONS, dc_prefix, load_season
from standing_prediction.data import standings_from_matches
from standing_prediction.defaults import DEFAULT_FIT, DEFAULT_WEIGHTS, DEFAULT_XG_SCALE, DEFAULT_XG_WEIGHT
from standing_prediction.predict_positions import build_fixture_specs, fit_model_components
from standing_prediction.simulate import simulate_season_scores
from standing_prediction.xg import blend_xg_strengths

LOG = logging.getLogger(__name__)
SEED, N_SIM = 7, 4000
# Stakes are computed once at least this share of the season's fixtures is played.
FIRST_SHARE = 0.5
# A conditional chance needs this many simulations behind its result.
MIN_SIMS = 50
EVENTS = ("title", "top4", "top6", "releg")
# Primary threshold fixed before results: a side has nothing to play for when no result of this fixture moves any
# of its four chances by 3 points or more. 1 and 10 points are reported as sensitivities.
LOW = 0.03
SENSITIVITY = (0.01, 0.10)


def events(places, teams):
    n = len(teams)
    return {"title": places == 0, "top4": places < 4, "top6": places < 6, "releg": places >= n - 3}


def swings(outcomes, places, teams, side_index):
    # For each tracked fixture and side, the largest change in each chance between two of its results.
    chances = events(places, teams)
    rows = []
    for f, (home, away) in enumerate(side_index):
        masks = [outcomes[:, f] == o for o in range(3)]
        known = [o for o, mask in enumerate(masks) if mask.sum() >= MIN_SIMS]
        row = {}
        for side, t in (("home", home), ("away", away)):
            for name, event in chances.items():
                values = [event[masks[o], t].mean() for o in known]
                row[f"{side}_{name}"] = float(max(values) - min(values)) if len(values) >= 2 else np.nan
                row[f"{side}_{name}_p"] = float(event[:, t].mean())
        rows.append(row)
    return rows


def build_part(league, season, out_dir, dataset_path, n_sim=N_SIM, seed=SEED):
    path = Path(out_dir) / f"{league}_{season}.csv"
    if path.exists():
        return pd.read_csv(path)
    competition = XG_COMPETITIONS[league]
    history = {year: load_season(league, year) for year in range(max(2014, season - DEFAULT_FIT["prior_seasons"]), season + 1)}
    matches = history[season]
    prior = pd.concat(history.values(), ignore_index=True)
    teams = sorted(set(matches["homeTeam"]) | set(matches["awayTeam"]))
    probabilities = [*(f"{dc_prefix(DEFAULT_XG_WEIGHT, DEFAULT_XG_SCALE)}_{c}" for c in "hda"), *(f"elo_{c}" for c in "hda")]
    saved = pd.read_csv(dataset_path, usecols=["league", "season", "homeTeam", "awayTeam", *probabilities])
    saved = saved[saved["league"].eq(league) & saved["season"].eq(season)].set_index(["homeTeam", "awayTeam"])[probabilities]
    rows = []
    for cutoff, future in matches.groupby("forecast_at", sort=True):
        known = (matches["available_at"] <= cutoff) & (matches["utcDate"] < cutoff)
        if known.mean() < FIRST_SHARE:
            continue
        played, remaining = matches[known], matches[~known].reset_index(drop=True)
        train = prior[(prior["available_at"] <= cutoff) & (prior["utcDate"] < cutoff)]
        dc, elo, xg, _ = fit_model_components(train, teams=teams, reference_date=cutoff, xi=DEFAULT_FIT["xi"],
                                             lambda_reg=DEFAULT_FIT["lambda_reg"], xg=True)
        dc = blend_xg_strengths(dc, xg, DEFAULT_XG_WEIGHT, DEFAULT_XG_SCALE)
        specs = build_fixture_specs(remaining, dc=dc, elo=elo, odds=None, max_goals=10, weights=DEFAULT_WEIGHTS)
        keys = set(zip(future["homeTeam"], future["awayTeam"]))
        tracked = [i for i, row in remaining.iterrows() if (row.homeTeam, row.awayTeam) in keys]
        if len(tracked) != len(future):
            raise ValueError(f"{league}/{season} {cutoff}: tracked fixtures differ from the origin's fixtures.")
        standings = standings_from_matches(played, teams=teams, competition=competition)
        counts, _, details = simulate_season_scores(specs, standings, n_sim=n_sim, seed=seed, played_matches=played,
                                                    competition=competition, return_details=True, track=tracked)
        order = list(counts.index)
        pairs = [(order.index(remaining.at[i, "homeTeam"]), order.index(remaining.at[i, "awayTeam"])) for i in tracked]
        for i, values in zip(tracked, swings(details["outcomes"], details["places"], order, pairs)):
            home, away = remaining.at[i, "homeTeam"], remaining.at[i, "awayTeam"]
            # The refit must reproduce the saved dataset's goal/xG and Elo probabilities for this fixture.
            refit = (*dc.match_outcome_probs(home, away), *elo.predict_probs(home, away))
            if not np.allclose(refit, saved.loc[(home, away)].to_numpy(float), atol=1e-9):
                raise ValueError(f"{league}/{season} {home}-{away}: refit differs from the saved dataset.")
            rows.append({"league": league, "season": season, "forecast_at": cutoff.isoformat(), "homeTeam": home, "awayTeam": away,
                         "played_share": float(known.mean()), "remaining": len(remaining), **values})
    frame = pd.DataFrame(rows)
    frame.to_csv(path, index=False)
    LOG.info("Built %s/%s: %s fixtures.", league, season, len(frame))
    return frame


def build(dataset_path, out_dir, workers):
    out = Path(out_dir) / "parts"
    out.mkdir(parents=True, exist_ok=True)
    seasons = sorted(pd.read_csv(dataset_path, usecols=["season"])["season"].unique())
    jobs = [(league, int(season)) for league in CALIBRATION_LEAGUES for season in seasons]
    with ProcessPoolExecutor(workers) as pool:
        frames = list(pool.map(build_part, *zip(*jobs), [out] * len(jobs), [dataset_path] * len(jobs)))
    return pd.concat(frames, ignore_index=True)


# Evaluation: the published no-odds blend plus stakes terms, fitted on earlier seasons and scored on the next.
def _log(p):
    return np.log(np.clip(p, 1e-12, 1))


def stake(frame, side):
    return frame[[f"{side}_{name}" for name in EVENTS]].max(axis=1, skipna=True).fillna(0.0)


def design(frame, threshold):
    # Asymmetry: +1 when only the away side has nothing to play for, -1 when only the home side has nothing.
    low_home, low_away = stake(frame, "home").lt(threshold), stake(frame, "away").lt(threshold)
    one = (low_away & ~low_home).astype(float) - (low_home & ~low_away).astype(float)
    both = (low_home & low_away).astype(float)
    x = np.zeros((len(frame), 3, 2))
    x[:, 0, 0], x[:, 2, 0] = one, -one
    x[:, 1, 1] = both
    return x


def losses(logits, y):
    return logsumexp(logits, axis=1) - logits[np.arange(len(y)), y]


def fit_shift(base, x, y, weights):
    actual = np.eye(3)[y]

    def objective(theta):
        logits = base + x @ theta
        residual = np.exp(logits - logsumexp(logits, axis=1, keepdims=True)) - actual
        return float(weights @ losses(logits, y)), np.einsum("n,nk,nkj->j", weights, residual, x)

    fit = minimize(objective, np.zeros(x.shape[-1]), jac=True, method="L-BFGS-B", options={"ftol": 1e-13, "gtol": 1e-9})
    if np.abs(objective(fit.x)[1]).max() > 1e-6:
        raise RuntimeError(f"Stakes fit failed: {fit.message}")
    return fit.x


def balance(frame):
    counts = frame.groupby(["league", "season"])["y"].transform("size").to_numpy(dtype=float)
    return (1 / counts) / (1 / counts).sum()


def compare(frame, scores, baseline, mask=None):
    # Equal league-season weights; SEs of differences cluster by league-season.
    frame = frame if mask is None else frame[mask]
    scores = {k: v if mask is None else v[mask.to_numpy()] for k, v in scores.items()}
    means = pd.DataFrame(scores, index=frame.index).groupby([frame["league"], frame["season"]]).mean()
    out = {}
    for name in means:
        difference = means[name] - means[baseline]
        out[name] = {"log_loss": float(means[name].mean()), "change": float(difference.mean()),
                     "se": float(difference.std(ddof=1) / np.sqrt(len(difference))), "better": int((difference < 0).sum()),
                     "clusters": len(difference), "matches": len(frame)}
    return out


def evaluate(data, stakes, share, first_test=2017):
    prefix = dc_prefix(DEFAULT_XG_WEIGHT, DEFAULT_XG_SCALE)
    frame = data.merge(stakes, on=["league", "season", "forecast_at", "homeTeam", "awayTeam"], how="left", validate="one_to_one")
    frame["has_stakes"] = frame["played_share"].notna()
    model = share * _log(frame[[f"{prefix}_{c}" for c in "hda"]].to_numpy(dtype=float)) + \
        (1 - share) * _log(frame[[f"elo_{c}" for c in "hda"]].to_numpy(dtype=float))
    quoted = frame[[f"book_{c}" for c in "hda"]].notna().all(axis=1).to_numpy()
    book = _log(frame[[f"book_{c}" for c in "hda"]].fillna(1 / 3).to_numpy(dtype=float))
    y = frame["y"].to_numpy(dtype=int)
    report = {"matches": len(frame), "with_stakes": int(frame["has_stakes"].sum()), "thresholds": {}}
    for threshold in (LOW, *SENSITIVITY):
        x = design(frame.fillna({c: 0.0 for c in frame.columns if c.startswith(("home_", "away_"))}), threshold)
        x[~frame["has_stakes"].to_numpy()] = 0
        test = frame["season"].ge(first_test).to_numpy()
        scores = {name: np.full(len(frame), np.nan) for name in ("model", "model_stakes", "book", "book_stakes")}
        folds = []
        for season in sorted(frame.loc[test, "season"].unique()):
            train, held = (frame["season"] < season).to_numpy(), (frame["season"] == season).to_numpy()
            theta = fit_shift(model[train], x[train], y[train], balance(frame[train]))
            market = train & quoted
            theta_book = fit_shift(book[market], x[market], y[market], balance(frame[market]))
            scores["model"][held] = losses(model[held], y[held])
            scores["model_stakes"][held] = losses(model[held] + x[held] @ theta, y[held])
            scores["book"][held] = losses(book[held], y[held])
            scores["book_stakes"][held] = losses(book[held] + x[held] @ theta_book, y[held])
            folds.append({"season": int(season), "model": theta.tolist(), "book": theta_book.tolist()})
        tested = frame[test].reset_index(drop=True)
        held_scores = {k: v[test] for k, v in scores.items()}
        quoted_test = pd.Series(quoted[test])
        flags = pd.Series(np.abs(x[test]).sum(axis=(1, 2)) > 0)
        late = pd.to_datetime(tested["forecast_at"], utc=True).dt.month.isin([4, 5, 6])
        result = {"folds": folds, "flagged_share": float(flags.mean()),
                  "all": compare(tested, {k: held_scores[k] for k in ("model", "model_stakes")}, "model"),
                  "flagged": compare(tested, {k: held_scores[k] for k in ("model", "model_stakes")}, "model", flags),
                  "apr_jun": compare(tested, {k: held_scores[k] for k in ("model", "model_stakes")}, "model", late)}
        # The market check scores only quoted fixtures.
        result["market"] = {"all": compare(tested, {k: held_scores[k] for k in ("book", "book_stakes")}, "book", quoted_test),
                            "flagged": compare(tested, {k: held_scores[k] for k in ("book", "book_stakes")}, "book", quoted_test & flags)}
        # Gap to the market by stakes group, on quoted fixtures.
        gap = pd.Series(held_scores["model"] - held_scores["book"])
        low_home = stake(tested, "home").lt(threshold) & tested["has_stakes"]
        low_away = stake(tested, "away").lt(threshold) & tested["has_stakes"]
        groups = {"no stakes computed": ~tested["has_stakes"], "both play for something": tested["has_stakes"] & ~low_home & ~low_away,
                  "one side has nothing": low_home ^ low_away, "neither has anything": low_home & low_away}
        result["gap"] = {}
        for name, mask in groups.items():
            used = mask & quoted_test
            means = gap[used].groupby([tested.loc[used, "league"], tested.loc[used, "season"]]).mean()
            result["gap"][name] = {"matches": int(used.sum()), "gap": float(means.mean()),
                                   "se": float(means.std(ddof=1) / np.sqrt(len(means))) if len(means) > 1 else None}
        report["thresholds"][str(threshold)] = result
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="R3: do low-stakes fixtures explain the late-season model-market gap?")
    parser.add_argument("--dataset", type=Path, default=Path("out/global-calibration/features/dataset.csv"))
    parser.add_argument("--artifact", type=Path, default=Path("src/standing_prediction/calibrated_weights.json"))
    parser.add_argument("--out-dir", type=Path, default=Path("out/late-stakes"))
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    artifact = json.loads(args.artifact.read_text())
    digest = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    if digest != artifact["dataset"]["sha256"]:
        raise ValueError("Dataset hash differs from the calibration artifact.")
    stakes = build(args.dataset, args.out_dir, args.workers)
    stakes.to_csv(args.out_dir / "stakes.csv", index=False)
    data = pd.read_csv(args.dataset)
    report = {"dataset_sha256": digest, "artifact_version": artifact["version"], "n_sim": N_SIM, "seed": SEED,
              "first_share": FIRST_SHARE, "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              **evaluate(data, stakes, artifact["no_odds_weights"]["main"])}
    path = args.out_dir / "results.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    LOG.info("Wrote %s.", path)


if __name__ == "__main__":
    main()
