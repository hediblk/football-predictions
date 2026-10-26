from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from forecast_calibration.dataset import XG_COMPETITIONS, dc_prefix, feature_code_hash, load_season
from standing_prediction.match_forecasts import describe_match
from standing_prediction.odds import FOOTBALL_DATA_UK_BASE, _football_data_uk_season_code
from standing_prediction.predict_positions import fit_model_components
from standing_prediction.utils import cache_max_age, cached_get
from standing_prediction.xg import COMPETITION_TO_UNDERSTAT_LEAGUE, blend_xg_strengths

ROOT = Path(__file__).resolve().parents[4]
ARTIFACT = ROOT / "src/standing_prediction/calibrated_weights.json"
MATCH_KEYS = ["utcDate", "homeTeam", "awayTeam"]
OUTPUT_COLUMNS = [
    "league", "season", "utcDate", "forecast_at", "homeTeam", "awayTeam", "homeGoals", "awayGoals",
    "home_xg", "away_xg", "p_h", "p_d", "p_a", "elo_h", "elo_d", "elo_a", "exp_home", "exp_away",
]


def _read_part(path):
    return pd.read_csv(path, parse_dates=["utcDate", "forecast_at"], float_precision="round_trip")


def _digest(content):
    if isinstance(content, str):
        content = content.encode()
    return hashlib.sha256(content).hexdigest()


def _cache_content(cache_dir, url, **kwargs):
    folder = "understat" if "understat.com/" in url else "football-data-uk"
    params = kwargs.get("params") or {}
    key = _digest(json.dumps([url, params], sort_keys=True).encode())
    return json.loads((cache_dir / folder / f"{key}.json").read_text())["content"]


def _load_content(cache_dir, url, offline):
    if offline:
        try:
            return _cache_content(cache_dir, url)
        except (OSError, ValueError, KeyError, TypeError):
            raise FileNotFoundError(f"Missing cached replay input: {url}") from None
    path_parts = url.rstrip("/").split("/")
    season = int(path_parts[-1]) if "understat.com/" in url else 2000 + int(path_parts[-2][:2])
    folder = "understat" if "understat.com/" in url else "football-data-uk"
    try:
        return cached_get(url, cache_dir=str(cache_dir / folder), max_age=cache_max_age(season))
    except RuntimeError as exc:
        raise RuntimeError(f"Replay source unavailable: {url} ({exc})") from None


def _input_urls(league, season, prior_seasons):
    first = max(2014, season - prior_seasons)
    csv_urls = [f"{FOOTBALL_DATA_UK_BASE}/{_football_data_uk_season_code(year)}/{league}.csv"
                for year in range(first, season + 1)]
    competition = XG_COMPETITIONS[league]
    understat = COMPETITION_TO_UNDERSTAT_LEAGUE[competition]
    xg_urls = [f"https://understat.com/getLeagueData/{understat}/{year}"
               for year in range(first, season + 1)]
    return [*csv_urls, *xg_urls]


def _model_inputs(history, origin, teams, settings, artifact):
    prior = pd.concat(history, ignore_index=True)
    train = prior[(prior.available_at <= origin) & (prior.utcDate < origin)]
    if train.empty:
        raise ValueError(f"No eligible training results before {origin}.")
    dc, elo, xg, _ = fit_model_components(
        train, teams=teams, reference_date=origin, xi=settings["xi"],
        lambda_reg=settings["lambda_reg"], xg=True,
    )
    model = blend_xg_strengths(dc, xg, artifact["xg_weight"], artifact["xg_scale"])
    return train, model, elo


def replay_season(league, season, cache_dir, out_dir, features=None, offline=True):
    cache_dir = Path(cache_dir).resolve()
    out_dir = Path(out_dir).resolve()
    artifact_data = json.loads(ARTIFACT.read_text())
    settings = artifact_data["fit_settings"]
    history_start = max(2014, season - settings["prior_seasons"])
    urls = _input_urls(league, season, settings["prior_seasons"])
    contents = {url: _load_content(cache_dir, url, offline) for url in urls}
    feature_hash = _digest(features.to_csv(index=False).encode()) if features is not None else None
    signature = {
        "inputs": {url: _digest(content) for url, content in contents.items()},
        "artifact": _digest(ARTIFACT.read_bytes()),
        "code": _digest(Path(__file__).read_bytes()),
        "match_forecasts_code": _digest((ROOT / "src/standing_prediction/match_forecasts.py").read_bytes()),
        "feature_code": feature_code_hash(),
        "features": feature_hash,
    }
    part = out_dir / "parts" / f"{league}_{season}.csv"
    stamp = part.with_suffix(".json")
    if part.exists() and stamp.exists():
        try:
            saved = json.loads(stamp.read_text())
            if saved["signature"] == signature and saved["output_sha256"] == _digest(part.read_bytes()):
                return _read_part(part)
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def read_cached(url, **kwargs):
        if url in contents:
            return contents[url]
        if offline:
            raise FileNotFoundError(f"Missing cached replay input: {url}")
        cache_folder = "understat" if "understat.com/" in url else "football-data-uk"
        kwargs.pop("cache_dir", None)
        return cached_get(url, cache_dir=str(cache_dir / cache_folder), **kwargs)

    with patch("standing_prediction.odds.cached_get", read_cached), patch("standing_prediction.xg.cached_get", read_cached):
        history = [load_season(league, year) for year in range(history_start, season + 1)]
    matches = history[-1]
    teams = sorted(set(matches.homeTeam) | set(matches.awayTeam))

    if features is not None:
        selected = features[(features.league == league) & (features.season == season)].copy()
        if selected.empty:
            raise ValueError(f"No saved calibration features for {league}/{season}.")
        selected["utcDate"] = pd.to_datetime(selected.utcDate, utc=True)
        source = selected.merge(matches, on=MATCH_KEYS, suffixes=("", "_source"), validate="one_to_one")
        if len(source) != len(selected):
            raise ValueError(f"Saved features do not cover the source fixtures for {league}/{season}.")
        truth = np.where(source.homeGoals > source.awayGoals, 0,
                         np.where(source.homeGoals == source.awayGoals, 1, 2))
        if not np.array_equal(truth, source.y.to_numpy()):
            raise ValueError(f"Results differ from saved features for {league}/{season}.")
        source = source.sort_values("forecast_at").reset_index(drop=True)
    else:
        source = matches.copy()

    rows = []
    for origin, group in source.groupby("forecast_at", sort=True):
        cutoff = pd.to_datetime(origin, utc=True)
        if not (pd.to_datetime(group.utcDate, utc=True) > cutoff).all():
            raise ValueError(f"Forecast origin is at or after kickoff for {league}/{season}.")
        train, model, elo = _model_inputs(history, cutoff, teams, settings, artifact_data)
        if features is not None:
            last_available = train.available_at.max()
            if not group.training_matches.eq(len(train)).all() or not pd.to_datetime(
                group.training_last_available_at, utc=True
            ).eq(last_available).all():
                raise ValueError(f"Training provenance differs from saved features for {league}/{season}.")
        for match in group.to_dict("records"):
            home, away = match["homeTeam"], match["awayTeam"]
            dc_probs = np.asarray(model.match_outcome_probs(home, away), dtype=float)
            elo_probs = np.asarray(elo.predict_probs(home, away), dtype=float)
            if features is not None:
                prefix = dc_prefix(artifact_data["xg_weight"], artifact_data["xg_scale"])
                saved_dc = np.asarray([match[f"{prefix}_{c}"] for c in "hda"], dtype=float)
                saved_elo = np.asarray([match[f"elo_{c}"] for c in "hda"], dtype=float)
                drift = max(np.max(np.abs(dc_probs - saved_dc)), np.max(np.abs(elo_probs - saved_elo)))
                if drift > 1e-6:
                    raise ValueError(f"Replay probability drift {league}/{season}: {drift}")
                dc_probs = saved_dc
                elo_probs = saved_elo
            weights = artifact_data["no_odds_weights"]
            logits = weights["main"] * np.log(np.clip(dc_probs, 1e-12, 1))
            logits += weights["elo"] * np.log(np.clip(elo_probs, 1e-12, 1))
            probabilities = np.exp(logits)
            probabilities /= probabilities.sum()
            _, matrix = model.score_matrix(home, away)
            described = describe_match(matrix, probabilities)
            rows.append({
                "league": league, "season": season, "utcDate": match["utcDate"], "forecast_at": cutoff,
                "homeTeam": home, "awayTeam": away,
                "homeGoals": match["homeGoals"], "awayGoals": match["awayGoals"],
                "home_xg": match["home_xg"], "away_xg": match["away_xg"],
                **dict(zip(("p_h", "p_d", "p_a"), probabilities)),
                **dict(zip(("elo_h", "elo_d", "elo_a"), elo_probs)),
                "exp_home": described["exp_home_goals"], "exp_away": described["exp_away_goals"],
            })

    frame = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    part.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(part, index=False)
    stamp.write_text(json.dumps({"signature": signature, "output_sha256": _digest(part.read_bytes())}, indent=2) + "\n")
    return _read_part(part)
