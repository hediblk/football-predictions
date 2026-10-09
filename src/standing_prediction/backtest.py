from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.metrics import log_loss

from standing_prediction.calibration import train_outcome_calibrator
from standing_prediction.data import FootballDataClient, standings_from_matches, validate_schedule
from standing_prediction.ensemble import blend_probabilities
from standing_prediction.odds import match_odds
from standing_prediction.h2h import encounter_residuals
from standing_prediction.predict_positions import (
    DEFAULT_H2H, DEFAULT_WEIGHTS, _parse_weights, build_fixture_specs, fit_prediction_models,
    load_h2h_results, load_history, load_season_results,
    predict_outcome_probs,
)
from standing_prediction.simulate import rank_table, simulate_season_scores


LOG = logging.getLogger(__name__)


def snapshot_split(matches, cutoff_matchday):
    """Teams, forecast origin, and played/future matches for a historical cutoff round, or None."""
    matches = matches.copy()
    matches["utcDate"] = pd.to_datetime(matches["utcDate"], utc=True)
    if matches["utcDate"].isna().any() or matches[["homeGoals", "awayGoals"]].isna().any().any():
        raise ValueError("Historical snapshots require dated, completed matches.")
    matches = matches.sort_values("utcDate").reset_index(drop=True)
    teams = sorted(set(matches["homeTeam"]) | set(matches["awayTeam"]))
    target_count = cutoff_matchday * (len(teams) // 2)
    if target_count < 1:
        raise ValueError("Cutoff rounds must be positive.")
    if target_count >= len(matches):
        return None
    # The end of this UTC day is a real forecast origin, including rescheduled games by date.
    cutoff = matches.iloc[target_count - 1]["utcDate"].normalize() + pd.Timedelta(days=1)
    train = matches[matches["utcDate"] < cutoff].copy()
    future = matches[matches["utcDate"] >= cutoff].copy()
    if future.empty:
        return None
    return teams, cutoff, train, future


def snapshot_features(matches, *, season, competition="PD", cutoff_matchday=10,
                      history=None, xi=0.003, lambda_reg=0.1, weights=None, odds=None,
                      xg_weight=0.0, h2h_weight=0.0, h2h_residuals=None):
    split = snapshot_split(matches, cutoff_matchday)
    if split is None:
        return pd.DataFrame(), None, None, None
    teams, cutoff, train, future = split
    standings = standings_from_matches(train, teams=teams, competition=competition)
    dc, elo = fit_prediction_models(train, teams=teams, history=history, reference_date=cutoff, xi=xi, lambda_reg=lambda_reg,
                                    xg_weight=xg_weight, h2h_weight=h2h_weight, h2h_residuals=h2h_residuals)
    lookup = match_odds(future, odds, as_of=cutoff) if odds is not None else {}
    rows = []
    for match in future.itertuples():
        p_dc = dc.match_outcome_probs(match.homeTeam, match.awayTeam)
        p_elo = elo.predict_probs(match.homeTeam, match.awayTeam)
        p_book = lookup.get((match.homeTeam, match.awayTeam))
        p_blend = blend_probabilities(p_dc, p_odds=p_book, p_elo=p_elo, weights=weights or DEFAULT_WEIGHTS)
        row = {"season": season, "cutoff_round": cutoff_matchday, "forecast_at": cutoff.isoformat(),
               "utcDate": match.utcDate.isoformat(), "homeTeam": match.homeTeam, "awayTeam": match.awayTeam,
               "y": 0 if match.homeGoals > match.awayGoals else 1 if match.homeGoals == match.awayGoals else 2}
        for name, probabilities in [("dc", p_dc), ("elo", p_elo), ("book", p_book or (np.nan,) * 3), ("blend", p_blend)]:
            row.update({f"{name}_{outcome}": value for outcome, value in zip("hda", probabilities)})
        rows.append(row)
    return pd.DataFrame(rows), standings, future, (dc, elo, cutoff)


def match_metrics(frame):
    results = {}
    y = frame["y"].to_numpy(dtype=int)
    actual = np.eye(3)[y]
    for name in ["dc", "elo", "blend", "calibrated"]:
        columns = [f"{name}_{outcome}" for outcome in "hda"]
        if not set(columns).issubset(frame.columns):
            continue
        p = frame[columns].to_numpy(dtype=float)
        results[f"{name}_log_loss"] = float(log_loss(y, p, labels=[0, 1, 2]))
        results[f"{name}_brier"] = float(np.mean(np.square(p - actual).sum(axis=1)))
    available = np.isfinite(frame[[f"book_{outcome}" for outcome in "hda"]]).all(axis=1)
    results["odds_matched"] = int(available.sum())
    if available.any():
        for name in ["dc", "elo", "blend", "book"]:
            p = frame.loc[available, [f"{name}_{outcome}" for outcome in "hda"]].to_numpy(dtype=float)
            results[f"{name}_log_loss_odds_subset"] = float(log_loss(y[available], p, labels=[0, 1, 2]))
    return results


def position_metrics(probabilities, points, actual_order, actual_standings):
    n_teams = len(probabilities)
    rank = np.array([actual_order.index(team) + 1 for team in probabilities.index])
    p = probabilities.to_numpy(dtype=float)
    cumulative_actual = np.arange(1, n_teams + 1)[None, :] >= rank[:, None]
    cdf = p.cumsum(axis=1)
    actual_points = actual_standings.set_index("team").loc[probabilities.index, "points"].to_numpy()
    results = {
        "position_rps": float(np.square(cdf[:, :-1] - cumulative_actual[:, :-1]).sum(axis=1).mean() / (n_teams - 1)),
        "position_log_loss": float(-np.log(np.clip(p[np.arange(n_teams), rank - 1], 1e-12, 1)).mean()),
        "expected_position_mae": float(np.abs(p @ np.arange(1, n_teams + 1) - rank).mean()),
        "expected_points_mae": float(np.abs(points.mean(axis=0) - actual_points).mean()),
    }
    for name, predicted, actual in [
        ("title", p[:, 0], rank == 1),
        ("top_four", p[:, :min(4, n_teams)].sum(axis=1), rank <= min(4, n_teams)),
        ("bottom_three", p[:, max(0, n_teams - 3):].sum(axis=1), rank > max(0, n_teams - 3)),
    ]:
        results[f"{name}_brier"] = float(np.square(predicted - actual).mean())
    return results


def run_backtest(*, competition="PD", seasons, cutoffs=(5, 10, 20, 30), n_sim=2000,
                 seed=7, prior_seasons=2, xi=0.003, lambda_reg=0.1,
                 weights=None, odds_snapshot=None, use_odds=False, out_dir=Path("out/backtests"), cache=True,
                 xg_weight=0.0, h2h_weight=0.0, h2h_seasons=DEFAULT_H2H["seasons"]):
    if n_sim < 1 or prior_seasons < 0:
        raise ValueError("n_sim must be positive; prior_seasons cannot be negative.")
    client = FootballDataClient(use_cache=cache) if os.getenv("FOOTBALL_DATA_API_KEY") else None
    odds = pd.read_csv(odds_snapshot) if use_odds and odds_snapshot else None
    if use_odds and odds is None:
        LOG.warning("No timestamped odds snapshot supplied; excluding historical CSV odds from dated forecasts.")
    prior_frames, forecast_frames, reports = [], [], []
    position_frames = []
    residuals = None
    if h2h_weight:
        residuals = encounter_residuals(load_h2h_results(client, competition, max(seasons) + 1, cache=cache,
                                                         seasons=h2h_seasons + max(seasons) - min(seasons)),
                                        xi=xi, lambda_reg=lambda_reg)
    for season in sorted(set(seasons)):
        matches = load_season_results(client, competition, season, cache=cache, xg=xg_weight > 0)
        teams = sorted(set(matches["homeTeam"]) | set(matches["awayTeam"]))
        actual_standings = standings_from_matches(matches, teams=teams, competition=competition)
        complete = matches.assign(status="FINISHED")
        validate_schedule(complete, actual_standings)
        actual_order = rank_table(actual_standings, matches, competition=competition)
        history = load_history(client, competition, season, teams, prior_seasons=prior_seasons, cache=cache, xg=xg_weight > 0)
        calibrator = None
        if prior_frames:
            calibrator = train_outcome_calibrator(pd.concat(prior_frames, ignore_index=True), use_odds_features=use_odds)
        season_frames = []
        for cutoff_round in cutoffs:
            frame, standings, future, models = snapshot_features(
                matches, season=season, competition=competition, cutoff_matchday=cutoff_round,
                history=history, xi=xi, lambda_reg=lambda_reg, weights=weights, odds=odds,
                xg_weight=xg_weight, h2h_weight=h2h_weight, h2h_residuals=residuals)
            if frame.empty:
                continue
            dc, elo, cutoff = models
            played = matches[pd.to_datetime(matches["utcDate"], utc=True) < cutoff]
            variants = [("blend", None)]
            if calibrator is not None:
                calibrated = [predict_outcome_probs(tuple(row[f"dc_{c}"] for c in "hda"),
                                                    tuple(row[f"elo_{c}"] for c in "hda"),
                                                    tuple(row[f"book_{c}"] for c in "hda") if np.isfinite(row["book_h"]) else None,
                                                    weights=weights, calibrator=calibrator)
                              for _, row in frame.iterrows()]
                frame[[f"calibrated_{c}" for c in "hda"]] = calibrated
                variants.append(("calibrated", calibrator))
            metrics = match_metrics(frame)
            for name, model in variants:
                specs = build_fixture_specs(future, dc=dc, elo=elo, odds=odds, as_of=cutoff,
                                             max_goals=10, weights=weights or DEFAULT_WEIGHTS, calibrator=model)
                counts, points = simulate_season_scores(specs, standings, n_sim=n_sim, seed=seed,
                                                        competition=competition, played_matches=played, return_details=True)
                p = counts / n_sim
                reports.append({"season": season, "cutoff_round": cutoff_round, "forecast_at": cutoff.isoformat(),
                                "model": name, "matches": len(frame), "n_sim": n_sim,
                                "match_log_loss": metrics[f"{name}_log_loss"], "match_brier": metrics[f"{name}_brier"],
                                **metrics, **position_metrics(p, points, actual_order, actual_standings)})
                saved = p.copy()
                saved.insert(0, "team", saved.index)
                saved.insert(0, "model", name)
                saved.insert(0, "forecast_at", cutoff.isoformat())
                saved.insert(0, "season", season)
                position_frames.append(saved.reset_index(drop=True))
            LOG.info("Season %s, cutoff %s: %s matches; blend log loss %.4f.", season, cutoff_round, len(frame), metrics["blend_log_loss"])
            season_frames.append(frame)
            forecast_frames.append(frame)
        prior_frames.extend(season_frames)
    if not reports:
        raise ValueError("No snapshots produced; use cutoffs within a completed season.")
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    report = pd.DataFrame(reports)
    report.to_csv(output / "metrics.csv", index=False)
    pd.concat(forecast_frames, ignore_index=True).to_csv(output / "match_forecasts.csv", index=False)
    pd.concat(position_frames, ignore_index=True).to_csv(output / "position_forecasts.csv", index=False)
    metadata = {"competition": competition, "seasons": sorted(set(seasons)), "cutoff_rounds": list(cutoffs),
                "n_sim": n_sim, "seed": seed, "prior_seasons": prior_seasons, "xi": xi, "lambda_reg": lambda_reg,
                "weights": weights or DEFAULT_WEIGHTS, "odds_snapshot": str(odds_snapshot) if odds_snapshot else None,
                "xg_weight": xg_weight, "h2h_weight": h2h_weight, "h2h_seasons": h2h_seasons if h2h_weight else None,
                "validation": "Expanding chronological seasons; first season has no calibrated evaluation.",
                "cutoff": "End of UTC day containing the Nth completed game (N = cutoff round × teams/2).",
                "position_log_loss": "Finite Monte Carlo zeros clipped at 1e-12; prefer RPS and event Brier scores.",
                "calibration": "Overlapping forecast horizons within each training season; held-out seasons stay strictly later."}
    metadata["historical_tables"] = "Reconstructed from match scores; disciplinary point deductions, appeals, fair-play rulings and playoff results are excluded."
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate dated match and final-position forecasts on completed seasons.")
    parser.add_argument("--competition", default="PD", choices=["PD", "PL", "BL1", "SA", "FL1"])
    parser.add_argument("--seasons", nargs="+", type=int, required=True)
    parser.add_argument("--cutoffs", "--cutoff-matchday", nargs="+", type=int, default=[5, 10, 20, 30])
    parser.add_argument("--n-sim", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--prior-seasons", type=int, default=2)
    parser.add_argument("--xi", type=float, default=0.003)
    parser.add_argument("--lambda-reg", type=float, default=0.1)
    parser.add_argument("--weights", default="main=0.35,odds=0.55,elo=0.10")
    parser.add_argument("--use-odds", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--odds-snapshot", type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path("out/backtests"))
    parser.add_argument("--xg-weight", type=float, default=0.0)
    parser.add_argument("--h2h-weight", type=float, default=0.0)
    parser.add_argument("--h2h-seasons", type=int, default=DEFAULT_H2H["seasons"])
    parser.add_argument("--cache", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args(argv)
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    options = vars(args)
    options["weights"] = _parse_weights(options["weights"])
    report = run_backtest(**options)
    columns = ["season", "cutoff_round", "model", "match_log_loss", "position_rps", "expected_points_mae", "title_brier", "top_four_brier", "bottom_three_brier"]
    print(report[columns].to_string(index=False, float_format=lambda value: f"{value:.4f}"))
    print(f"Wrote historical forecasts and metrics to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
