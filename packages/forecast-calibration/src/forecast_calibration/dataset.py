from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from standing_prediction.odds import _football_data_csv, _uk_dates
from standing_prediction.predict_positions import fit_model_components
from standing_prediction.utils import normalize_team
from standing_prediction.xg import attach_xg, blend_xg_strengths, fetch_understat_matches

LOG = logging.getLogger(__name__)
CALIBRATION_LEAGUES = ("E0", "SP1", "D1", "I1", "F1")
ROBUSTNESS_LEAGUES = ("P1", "N1", "B1", "T1", "G1", "SC0")
XG_COMPETITIONS = {"E0": "PL", "SP1": "PD", "D1": "BL1", "I1": "SA", "F1": "FL1"}
XG_GRID = (0.0, 0.25, 0.5, 0.75, 1.0)


def collection_time(dates):
    dates = pd.to_datetime(dates, utc=True).dt.tz_convert("Europe/London")
    day = pd.to_datetime(dates.dt.strftime("%Y-%m-%d"), utc=True)
    weekday = dates.dt.weekday
    days_back = np.where((weekday >= 4) | (weekday == 0), (weekday - 4) % 7, weekday - 1)
    return day - pd.to_timedelta(days_back, unit="D")


def load_season(league, season, *, cache=True):
    raw = _football_data_csv(league, season, 30, ".cache/football-data-uk", cache)
    matches = raw[["HomeTeam", "AwayTeam", "FTHG", "FTAG"]].rename(columns={
        "HomeTeam": "homeTeam", "AwayTeam": "awayTeam", "FTHG": "homeGoals", "FTAG": "awayGoals",
    }).copy()
    dates = _uk_dates(raw)
    match_day = pd.to_datetime(dates.dt.tz_convert("Europe/London").dt.strftime("%Y-%m-%d"), utc=True)
    has_time = raw["Time"].astype(str).str.fullmatch(r"\d{1,2}:\d{2}", na=False) if "Time" in raw else pd.Series(False, index=raw.index)
    matches["utcDate"] = dates.where(has_time, match_day + pd.Timedelta(hours=12))
    # Result and xG availability is conservatively the next UTC day after the local match date.
    matches["available_at"] = match_day + pd.Timedelta(days=1)
    matches["forecast_at"] = collection_time(dates)
    for column in ("homeTeam", "awayTeam"):
        matches[column] = matches[column].map(normalize_team)
    for column in ("homeGoals", "awayGoals"):
        matches[column] = pd.to_numeric(matches[column], errors="coerce")
    matches["odds_source"] = ""
    matches[[f"book_{c}" for c in "hda"]] = np.nan
    # Average prices first; never use closing columns or mix bookmakers within a quote.
    for prefix in ("Avg", "BbAv", "B365"):
        columns = [f"{prefix}{c}" for c in "HDA"]
        if not set(columns).issubset(raw.columns):
            continue
        decimal = raw[columns].apply(pd.to_numeric, errors="coerce")
        valid = np.isfinite(decimal).all(axis=1) & decimal.gt(1).all(axis=1) & matches["odds_source"].eq("")
        probabilities = 1 / decimal.loc[valid].to_numpy(dtype=float)
        probabilities /= probabilities.sum(axis=1, keepdims=True)
        matches.loc[valid, [f"book_{c}" for c in "hda"]] = probabilities
        matches.loc[valid, "odds_source"] = prefix
    matches = matches.dropna(subset=["homeGoals", "awayGoals", "utcDate"]).sort_values("utcDate").reset_index(drop=True)
    scores = matches[["homeGoals", "awayGoals"]].to_numpy(dtype=float)
    if (scores < 0).any() or (scores != np.floor(scores)).any():
        raise ValueError(f"Invalid scores in {league}/{season}.")
    if matches[["utcDate", "homeTeam", "awayTeam"]].duplicated().any():
        raise ValueError(f"Duplicate fixtures in {league}/{season}.")
    if league in XG_COMPETITIONS:
        xg = fetch_understat_matches(competition=XG_COMPETITIONS[league], season=season, use_cache=cache)
        matches = attach_xg(matches, xg)
    matches["season"] = season
    matches["league"] = league
    return matches


def build_dataset(*, leagues, seasons, out_dir, xg_grid=XG_GRID, prior_seasons=2, xi=0.003, lambda_reg=0.1, cache=True):
    seasons = sorted(set(seasons))
    leagues = list(dict.fromkeys(leagues))
    xg_grid = sorted(set(float(w) for w in xg_grid))
    if not seasons or not leagues or prior_seasons < 1 or not xg_grid or any(not 0 <= w <= 1 for w in xg_grid):
        raise ValueError("Provide leagues, seasons, a nonempty xG grid in [0, 1], and at least one prior season.")
    if seasons != list(range(min(seasons), max(seasons) + 1)):
        raise ValueError("Dataset seasons must be consecutive.")
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    config = {"schema_version": 1, "leagues": leagues, "seasons": seasons, "xg_grid": xg_grid,
              "prior_seasons": prior_seasons, "xi": xi, "lambda_reg": lambda_reg,
              "feature_code_sha256": feature_code_hash()}
    frames, coverage = [], []
    for league in leagues:
        # 2014/15 is the first xG season and the warm-up for the first calibration year.
        history_start = max(2014, min(seasons) - prior_seasons)
        history = {year: load_season(league, year, cache=cache) for year in range(history_start, max(seasons) + 1)}
        for year, matches in history.items():
            coverage.append({"league": league, "season": year, "matches": len(matches),
                             "odds": int(matches["book_h"].notna().sum()), "odds_sources": matches["odds_source"].value_counts().to_dict(),
                             "xg": matches.attrs.get("xg_coverage")})
        for season in seasons:
            part_path = output / f"{league}_{season}.csv"
            part_config = {**config, "league": league, "season": season}
            config_path = part_path.with_suffix(".json")
            if cache and part_path.exists() and config_path.exists() and json.loads(config_path.read_text()) == part_config:
                frame = pd.read_csv(part_path)
                LOG.info("Reused %s/%s: %s matches.", league, season, len(frame))
            else:
                matches = history[season]
                prior = pd.concat([history[y] for y in history if season - prior_seasons <= y <= season], ignore_index=True)
                rows = []
                teams = sorted(set(matches["homeTeam"]) | set(matches["awayTeam"]))
                for cutoff, future in matches.groupby("forecast_at", sort=True):
                    train = prior[(prior["available_at"] <= cutoff) & (prior["utcDate"] < cutoff)]
                    dc, elo, xg, _ = fit_model_components(train, teams=teams, reference_date=cutoff, xi=xi,
                                                         lambda_reg=lambda_reg, xg=league in XG_COMPETITIONS)
                    models = {w: blend_xg_strengths(dc, xg, w) for w in xg_grid}
                    for match in future.itertuples(index=False):
                        row = {"league": league, "season": season, "forecast_at": cutoff.isoformat(),
                               "utcDate": match.utcDate.isoformat(), "training_last_available_at": train["available_at"].max().isoformat(),
                               "training_matches": len(train), "homeTeam": match.homeTeam, "awayTeam": match.awayTeam,
                               "y": 0 if match.homeGoals > match.awayGoals else 1 if match.homeGoals == match.awayGoals else 2,
                               "odds_source": match.odds_source}
                        for c in "hda":
                            row[f"book_{c}"] = getattr(match, f"book_{c}")
                        row.update({f"elo_{c}": p for c, p in zip("hda", elo.predict_probs(match.homeTeam, match.awayTeam))})
                        for w, model in models.items():
                            row.update({f"dc_{w:g}_{c}": p for c, p in zip("hda", model.match_outcome_probs(match.homeTeam, match.awayTeam))})
                        rows.append(row)
                frame = pd.DataFrame(rows)
                frame.to_csv(part_path, index=False)
                config_path.write_text(json.dumps(part_config, indent=2) + "\n")
                LOG.info("Built %s/%s: %s matches, %s origins.", league, season, len(frame), matches["forecast_at"].nunique())
            frames.append(frame)
    dataset = pd.concat(frames, ignore_index=True)
    path = output / "dataset.csv"
    dataset.to_csv(path, index=False)
    metadata = {**config, "matches": len(dataset), "coverage": coverage,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "odds_timing": "Approximate preceding Tuesday/Friday 00:00 UTC; actual quotes collected that afternoon, not timestamped.",
                "result_timing": "Results and xG available next UTC day after local match date; unknown kickoffs anchored at 12:00 UTC.",
                "history": "Up to two prior seasons by default, starting in 2014/15; features use only results available at origin."}
    (output / "dataset.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return dataset, metadata


def feature_code_hash():
    import standing_prediction

    root = Path(standing_prediction.__file__).parent
    paths = [Path(__file__), *(root / name for name in ("dixon_coles.py", "elo.py", "xg.py", "odds.py", "utils.py", "predict_positions.py"))]
    return hashlib.sha256(b"".join(path.read_bytes() for path in paths)).hexdigest()
