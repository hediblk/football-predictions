import argparse
import hashlib
import io
import json
import platform
from pathlib import Path

import numpy as np
import pandas as pd

from forecast_calibration.dataset import dc_prefix
from standing_prediction.odds import FOOTBALL_DATA_UK_BASE, _uk_dates
from standing_prediction.utils import normalize_team

ROOT = Path(__file__).resolve().parents[4]
ARTIFACT = ROOT / "src/standing_prediction/calibrated_weights.json"
PICKS = ("market_favourite", "model_favourite", "edge_0", "edge_5", "edge_10", "disagreement")
BOOKS = {"average": {"pre": ("Avg", "BbAv"), "close": ("AvgC",)},
         "best": {"pre": ("Max", "BbMx"), "close": ("MaxC",)},
         "bet365": {"pre": ("B365",), "close": ("B365C",)}}
KEYS = ["league", "season", "homeTeam", "awayTeam"]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_matches(dataset, cache_dir):
    artifact = json.loads(ARTIFACT.read_text())
    if digest(dataset) != artifact["dataset"]["sha256"]:
        raise ValueError("Dataset hash differs from the saved calibration artifact")
    features = pd.read_csv(dataset)
    if features.duplicated(KEYS).any():
        raise ValueError("Duplicate forecast fixture")
    origin = pd.to_datetime(features.forecast_at, utc=True)
    kickoff = pd.to_datetime(features.utcDate, utc=True)
    if (origin >= kickoff).any() or (pd.to_datetime(features.training_last_available_at, utc=True) > origin).any():
        raise ValueError("Forecast or training availability extends beyond its cutoff")
    prefix = dc_prefix(artifact["xg_weight"], artifact["xg_scale"])
    logits = np.zeros((len(features), 3))
    weights = artifact["no_odds_weights"]
    for component, share in ((prefix, weights["main"]), ("elo", weights["elo"])):
        probabilities = features[[f"{component}_{side}" for side in "hda"]].to_numpy(float)
        if not np.isfinite(probabilities).all() or (probabilities < 0).any() or not np.allclose(probabilities.sum(axis=1), 1):
            raise ValueError("Invalid saved model probabilities")
        logits += share * np.log(np.clip(probabilities, 1e-12, 1))
    probabilities = np.exp(logits)
    features[[f"p_{side}" for side in "hda"]] = probabilities / probabilities.sum(axis=1, keepdims=True)
    features = features[KEYS + ["utcDate", "forecast_at", "y"] + [f"p_{side}" for side in "hda"]].copy()
    joined, coverage, unmatched, hashes = [], [], [], {}
    for (league, season), group in features.groupby(["league", "season"], sort=True):
        url = f"{FOOTBALL_DATA_UK_BASE}/{season % 100:02d}{(season + 1) % 100:02d}/{league}.csv"
        key = hashlib.sha256(json.dumps([url, {}], sort_keys=True).encode()).hexdigest()
        path = Path(cache_dir) / "football-data-uk" / f"{key}.json"
        content = json.loads(path.read_text())["content"]
        hashes[url] = hashlib.sha256(content.encode()).hexdigest()
        raw = pd.read_csv(io.StringIO(content))
        source = raw[["HomeTeam", "AwayTeam", "FTHG", "FTAG"]].rename(columns={
            "HomeTeam": "homeTeam", "AwayTeam": "awayTeam", "FTHG": "homeGoals", "FTAG": "awayGoals"})
        source["league"], source["season"] = league, season
        dates = _uk_dates(raw)
        has_time = raw.Time.astype(str).str.fullmatch(r"\d{1,2}:\d{2}", na=False) if "Time" in raw else pd.Series(False, index=raw.index)
        noon = pd.to_datetime(dates.dt.tz_convert("Europe/London").dt.strftime("%Y-%m-%d"), utc=True) + pd.Timedelta(hours=12)
        source["source_kickoff"] = dates.where(has_time, noon)
        for side in ("home", "away"):
            source[f"{side}Team"] = source[f"{side}Team"].map(normalize_team)
        for book, timings in BOOKS.items():
            for timing, prefixes in timings.items():
                columns = [f"{book}_{timing}_{side}" for side in "hda"]
                source[columns] = np.nan
                for price_prefix in prefixes:
                    names = [f"{price_prefix}{side}" for side in "HDA"]
                    if set(names).issubset(raw.columns):
                        prices = raw[names].apply(pd.to_numeric, errors="coerce").to_numpy(float)
                        valid = np.isfinite(prices).all(axis=1) & (prices > 1).all(axis=1) & source[columns].isna().all(axis=1)
                        source.loc[valid, columns] = prices[valid]
        matched = group.merge(source, on=KEYS, how="left", validate="one_to_one", indicator=True)
        missing = matched[matched._merge != "both"]
        unmatched.extend(missing[KEYS + ["utcDate"]].to_dict("records"))
        matched = matched[matched._merge == "both"].copy()
        if not pd.to_datetime(matched.utcDate, utc=True).eq(matched.source_kickoff).all():
            raise ValueError(f"Fixture dates differ: {league}/{season}")
        scores = matched[["homeGoals", "awayGoals"]].to_numpy(float)
        if not np.isfinite(scores).all() or (scores < 0).any() or (scores != np.floor(scores)).any():
            raise ValueError(f"Invalid result: {league}/{season}")
        truth = np.where(scores[:, 0] > scores[:, 1], 0, np.where(scores[:, 0] == scores[:, 1], 1, 2))
        if not np.array_equal(truth, matched.y):
            raise ValueError(f"Result differs from forecast target: {league}/{season}")
        for book in BOOKS:
            for timing in ("pre", "close"):
                priced = matched[[f"{book}_{timing}_{side}" for side in "hda"]].notna().all(axis=1)
                coverage.append({"league": league, "season": int(season), "book": book, "timing": timing,
                                 "forecasts": len(group), "matched": len(matched), "unmatched": len(missing),
                                 "priced": int(priced.sum()), "without_price": int((~priced).sum())})
        columns = KEYS + ["utcDate", "forecast_at", "y", "homeGoals", "awayGoals"]
        columns += [f"p_{side}" for side in "hda"]
        columns += [f"{book}_{timing}_{side}" for book in BOOKS for timing in ("pre", "close") for side in "hda"]
        joined.append(matched[columns])
    frame = pd.concat(joined, ignore_index=True).sort_values(["utcDate", "league", "homeTeam"]).reset_index(drop=True)
    frame["day"] = pd.to_datetime(frame.utcDate, utc=True).dt.strftime("%Y-%m-%d")
    provenance = {"calibration_version": artifact["version"], "artifact_sha256": digest(ARTIFACT),
                  "dataset_sha256": digest(dataset), "source_sha256": hashes}
    return frame, pd.DataFrame(coverage), pd.DataFrame(unmatched, columns=KEYS + ["utcDate"]), provenance


def select_bets(frame, book="average", timing="pre", pick="model_favourite"):
    if pick not in PICKS:
        raise ValueError(f"Unknown selection rule: {pick}")
    prices = frame[[f"{book}_{timing}_{side}" for side in "hda"]].to_numpy(float)
    probabilities = frame[[f"p_{side}" for side in "hda"]].to_numpy(float)
    valid = np.isfinite(prices).all(axis=1) & (prices > 1).all(axis=1)
    model = probabilities.argmax(axis=1)
    market = np.where(np.isfinite(prices), prices, np.inf).argmin(axis=1)
    edge = probabilities * prices - 1
    selection = np.where(np.isfinite(edge), edge, -np.inf).argmax(axis=1) if pick.startswith("edge_") else market if pick == "market_favourite" else model
    selected_edge = edge[np.arange(len(frame)), selection]
    if pick.startswith("edge_"):
        valid &= selected_edge >= int(pick.split("_")[1]) / 100
    elif pick == "disagreement":
        valid &= model != market
    rows = np.flatnonzero(valid)
    bets = frame.iloc[rows][KEYS + ["utcDate", "day", "y"]].copy()
    bets["bet_day"] = pd.to_datetime(frame.iloc[rows].forecast_at, utc=True).dt.strftime("%Y-%m-%d") if timing == "pre" else bets.day
    bets["selection"] = selection[rows]
    bets["price"] = prices[rows, selection[rows]]
    bets["probability"] = probabilities[rows, selection[rows]]
    bets["edge"] = selected_edge[rows]
    closing = frame[[f"{book}_close_{side}" for side in "hda"]].to_numpy(float)
    bets["closing_price"] = closing[rows, selection[rows]] if timing == "pre" else np.nan
    bets["won"] = bets.selection == bets.y
    bets["return"] = np.where(bets.won, bets.price - 1, -1)
    bets["price_band"] = pd.cut(bets.price, [1, 1.5, 2, 3, 5, np.inf], right=False,
                                labels=["1-1.5", "1.5-2", "2-3", "3-5", "5+"]).astype(str)
    return bets.reset_index(drop=True)


def stake_bets(bets, method="flat", bankroll=100, fraction=0.25, cap=0.03):
    if method not in ("flat", "quarter_kelly") or bankroll <= 0 or not 0 < fraction <= 1 or not 0 < cap <= 1:
        raise ValueError("Invalid staking settings")
    bets = bets.sort_values(["utcDate", "league", "homeTeam"]).reset_index(drop=True).copy()
    stakes = np.ones(len(bets))
    if method == "quarter_kelly":
        fractions = np.clip(fraction * bets.edge.to_numpy() / (bets.price.to_numpy() - 1), 0, cap)
        current_season, balance, settled_at = None, bankroll, None
        returns = bets["return"].to_numpy()
        for (season, day), indices in bets.groupby(["season", "bet_day"], sort=True).indices.items():
            if season != current_season:
                current_season, balance, settled_at = season, bankroll, None
            if settled_at is not None and settled_at > pd.Timestamp(day, tz="UTC"):
                raise ValueError("Overlapping betting batches need explicit reserved-cash settlement")
            sizes = fractions[indices]
            sizes = sizes / max(1, sizes.sum())
            stakes[indices] = balance * sizes
            balance += float(stakes[indices] @ returns[indices])
            settled_at = pd.to_datetime(bets.iloc[indices].utcDate, utc=True).max().normalize() + pd.Timedelta(days=1)
    bets["stake"] = stakes
    bets["profit"] = stakes * bets["return"].to_numpy()
    return bets[bets.stake > 0].reset_index(drop=True)


def summarize(bets, *, bootstrap=2000, seed=7):
    if bootstrap < 1:
        raise ValueError("Bootstrap replicate count must be positive")
    staked, profit = float(bets.stake.sum()), float(bets.profit.sum())
    daily = bets.groupby("day")[["stake", "profit"]].sum().to_numpy()
    interval = [None, None]
    if len(daily) > 1 and staked > 0:
        replicates = []
        for start in range(0, bootstrap, 200):
            count = min(200, bootstrap - start)
            sampled = daily[bootstrap_indices(seed, start, count, len(daily))].sum(axis=1)
            replicates.extend((sampled[:, 1] / sampled[:, 0]).tolist())
        interval = np.quantile(replicates, [0.025, 0.975]).tolist()
    closing = bets.closing_price.notna()
    drawdown, losing_run, run = 0.0, 0, 0
    for _, group in bets.groupby("season", sort=True):
        path = np.r_[0, group.groupby("day", sort=True).profit.sum().cumsum().to_numpy()]
        drawdown = max(drawdown, float((np.maximum.accumulate(path) - path).max()))
        run = 0
        for won in group.won:
            run = 0 if won else run + 1
            losing_run = max(losing_run, run)
    return {"bets": len(bets), "staked": staked, "profit": profit,
            "roi": profit / staked if staked else None, "roi_low": interval[0], "roi_high": interval[1],
            "clusters": len(daily), "strike_rate": float(bets.won.mean()) if len(bets) else None,
            "implied_strike_rate": float((1 / bets.price).mean()) if len(bets) else None,
            "average_price": float(bets.price.mean()) if len(bets) else None,
            "mean_edge": float(bets.edge.mean()) if len(bets) else None,
            "clv_bets": int(closing.sum()),
            "clv": float((bets.loc[closing, "price"] / bets.loc[closing, "closing_price"] - 1).mean()) if closing.any() else None,
            "max_drawdown_units": drawdown, "longest_losing_run": losing_run}


def bootstrap_indices(seed, start, count, clusters):
    # Mulberry32 uses the same 32-bit arithmetic as JavaScript's Math.imul.
    counter = np.arange(start * clusters + 1, (start + count) * clusters + 1, dtype=np.uint64)
    state = (seed + counter * 0x6D2B79F5).astype(np.uint32)
    bits = (state ^ (state >> 15)) * (state | 1)
    bits ^= bits + ((bits ^ (bits >> 7)) * (bits | 61))
    bits ^= bits >> 14
    return ((bits.astype(np.uint64) * clusters) >> 32).astype(np.intp).reshape(count, clusters)


def run_study(frame, *, bootstrap=2000, seed=7):
    summaries, breakdowns, audit = [], [], []
    for book in BOOKS:
        for timing in ("pre", "close"):
            priced = int(frame[[f"{book}_{timing}_{side}" for side in "hda"]].notna().all(axis=1).sum())
            for pick in PICKS:
                selected = select_bets(frame, book, timing, pick)
                for method in ("flat", "quarter_kelly"):
                    config = {"book": book, "timing": timing, "pick": pick, "staking": method}
                    bets = stake_bets(selected, method)
                    summaries.append({**config, "matches": len(frame), "priced": priced,
                                      **summarize(bets, bootstrap=bootstrap, seed=seed)})
                    for dimension in ("season", "league", "price_band"):
                        for value, group in bets.groupby(dimension, sort=True):
                            breakdowns.append({**config, "dimension": dimension, "value": str(value),
                                               **summarize(group, bootstrap=bootstrap, seed=seed)})
                    if book == "average" and timing == "pre":
                        audit.append(bets.assign(pick=pick, staking=method))
            print(f"{book}/{timing}: {priced}/{len(frame)} fixtures priced", flush=True)
    return pd.DataFrame(summaries), pd.DataFrame(breakdowns), pd.concat(audit, ignore_index=True)


def main():
    parser = argparse.ArgumentParser(description="Offline 1X2 betting feasibility study using the saved no-odds forecasts")
    parser.add_argument("--dataset", type=Path, default=ROOT / "out/global-calibration/features/dataset.csv")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / ".cache")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "out/backtest-feasibility")
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    if not 0 <= args.seed < 2**32:
        raise ValueError("Seed must be an unsigned 32-bit integer")
    output = args.out_dir.resolve()
    if output != ROOT / "out" and ROOT / "out" not in output.parents:
        raise ValueError("Historical price outputs must stay under out/ until publishing decision D1 is resolved")
    frame, coverage, unmatched, provenance = load_matches(args.dataset, args.cache_dir)
    summaries, breakdowns, audit = run_study(frame, bootstrap=args.bootstrap, seed=args.seed)
    output.mkdir(parents=True, exist_ok=True)
    for name, table in (("matches", frame), ("coverage", coverage), ("unmatched", unmatched),
                        ("summaries", summaries), ("breakdowns", breakdowns), ("bets", audit)):
        table.to_csv(output / f"{name}.csv", index=False)
    presets = summaries[(summaries.book == "average") & (summaries.timing == "pre")]
    (output / "parity.json").write_text(presets.to_json(orient="records", indent=2) + "\n")
    provenance.update(code_sha256=digest(__file__), seed=args.seed, bootstrap=args.bootstrap,
                      python=platform.python_version(), numpy=np.__version__, pandas=pd.__version__,
                      fixtures=len(frame), unmatched=len(unmatched), forecast_kind="replayed, in-sample for calibration",
                      timing="Pre-closing collection follows Tuesday/Friday origin, approximately; no quote timestamps. Closing is later, approximately.",
                      staking={"initial_bankroll_per_season": 100, "kelly_fraction": 0.25, "per_bet_cap": 0.03,
                               "daily_exposure_cap": 1, "sizing": "start of price day: origin day for pre, match day for close"},
                      bootstrap_unit="UTC match date, all leagues together; fixed realized stakes",
                      bootstrap_rng="Mulberry32; row-major draws; linear percentile interpolation",
                      output_sha256={p.name: digest(p) for p in sorted(output.glob("*.csv"))})
    (output / "provenance.json").write_text(json.dumps(provenance, indent=2, allow_nan=False) + "\n")
    print(f"Saved {len(summaries)} strategy summaries to {output}")


if __name__ == "__main__":
    main()
