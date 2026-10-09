from __future__ import annotations

import argparse
import itertools
import json
import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

from standing_prediction.backtest import match_metrics, position_metrics, snapshot_split
from standing_prediction.data import FootballDataClient, standings_from_matches
from standing_prediction.ensemble import blend_probabilities
from standing_prediction.h2h import encounter_residuals
from standing_prediction.predict_positions import (
    DEFAULT_H2H, DEFAULT_WEIGHTS, adjust_goal_model, build_fixture_specs, fit_model_components,
    load_h2h_results, load_history, load_season_results,
)
from standing_prediction.simulate import rank_table, simulate_season_scores


LOG = logging.getLogger(__name__)
METRICS = ["match_log_loss", "match_brier", "position_rps", "expected_points_mae", "title_brier", "top_four_brier", "bottom_three_brier"]


def _season_snapshots(client, competition, seasons, cutoffs, *, prior_seasons, xi, lambda_reg, residuals, cache):
    """Yield fitted components once per season/cutoff; variants reuse them."""
    for season in seasons:
        matches = load_season_results(client, competition, season, cache=cache, xg=True)
        teams = sorted(set(matches["homeTeam"]) | set(matches["awayTeam"]))
        history = load_history(client, competition, season, teams, prior_seasons=prior_seasons, cache=cache, xg=True)
        coverage = {season: matches.attrs.get("xg_coverage"), **history.attrs.get("xg_coverage", {})}
        for cutoff_round in cutoffs:
            split = snapshot_split(matches, cutoff_round)
            if split is None:
                continue
            teams, cutoff, train, future = split
            components = fit_model_components(train, teams=teams, history=history, reference_date=cutoff, xi=xi,
                                              lambda_reg=lambda_reg, xg=True, h2h_residuals=residuals)
            yield season, cutoff_round, matches, teams, cutoff, train, future, components, coverage


def _match_frame(future, dc, elo, weights):
    rows = []
    for match in future.itertuples():
        p_dc = dc.match_outcome_probs(match.homeTeam, match.awayTeam)
        p_elo = elo.predict_probs(match.homeTeam, match.awayTeam)
        p_blend = blend_probabilities(p_dc, p_elo=p_elo, weights=weights)
        row = {"y": 0 if match.homeGoals > match.awayGoals else 1 if match.homeGoals == match.awayGoals else 2}
        for name, probabilities in [("dc", p_dc), ("elo", p_elo), ("book", (np.nan,) * 3), ("blend", p_blend)]:
            row.update({f"{name}_{outcome}": value for outcome, value in zip("hda", probabilities)})
        rows.append(row)
    return pd.DataFrame(rows)


def tune(client, competition, seasons, cutoffs, *, xg_grid, h2h_grid, prior_seasons, xi, lambda_reg, residuals, weights, cache):
    """Blend match log loss for every (xG weight, head-to-head weight) pair on tuning seasons."""
    totals = {pair: [0.0, 0] for pair in itertools.product(xg_grid, h2h_grid)}
    for season, cutoff_round, _, teams, _, _, future, (dc, elo, xg, effects), _ in _season_snapshots(
            client, competition, seasons, cutoffs, prior_seasons=prior_seasons, xi=xi, lambda_reg=lambda_reg,
            residuals=residuals, cache=cache):
        for pair in totals:
            model = adjust_goal_model(dc, teams=teams, xg_strengths=xg, xg_weight=pair[0], h2h_effects=effects, h2h_weight=pair[1])
            frame = _match_frame(future, model, elo, weights)
            totals[pair][0] += match_metrics(frame)["blend_log_loss"] * len(frame)
            totals[pair][1] += len(frame)
        LOG.info("Tuned season %s, cutoff %s.", season, cutoff_round)
    grid = pd.DataFrame([{"xg_weight": w, "h2h_weight": b, "match_log_loss": loss / max(n, 1), "matches": n}
                         for (w, b), (loss, n) in totals.items()])
    return grid


def choose_variants(grid):
    def best(frame):
        row = frame.sort_values(["match_log_loss", "xg_weight", "h2h_weight"]).iloc[0]
        return float(row["xg_weight"]), float(row["h2h_weight"])

    return {
        "baseline": (0.0, 0.0),
        "xg": best(grid[grid["h2h_weight"] == 0]),
        "h2h": best(grid[grid["xg_weight"] == 0]),
        "both": best(grid),
    }


def evaluate(client, competition, seasons, cutoffs, variants, *, prior_seasons, xi, lambda_reg, residuals, weights,
             n_sim, seed, cache):
    reports, coverage = [], {}
    for season, cutoff_round, matches, teams, cutoff, train, future, (dc, elo, xg, effects), seen in _season_snapshots(
            client, competition, seasons, cutoffs, prior_seasons=prior_seasons, xi=xi, lambda_reg=lambda_reg,
            residuals=residuals, cache=cache):
        coverage.update(seen)
        actual_standings = standings_from_matches(matches, teams=teams, competition=competition)
        actual_order = rank_table(actual_standings, matches, competition=competition)
        standings = standings_from_matches(train, teams=teams, competition=competition)
        for name, (xg_weight, h2h_weight) in variants.items():
            model = adjust_goal_model(dc, teams=teams, xg_strengths=xg, xg_weight=xg_weight, h2h_effects=effects, h2h_weight=h2h_weight)
            metrics = match_metrics(_match_frame(future, model, elo, weights))
            specs = build_fixture_specs(future, dc=model, elo=elo, odds=None, max_goals=10, weights=weights)
            counts, points = simulate_season_scores(specs, standings, n_sim=n_sim, seed=seed, competition=competition,
                                                    played_matches=train, return_details=True)
            reports.append({"season": season, "cutoff_round": cutoff_round, "forecast_at": cutoff.isoformat(),
                            "variant": name, "xg_weight": xg_weight, "h2h_weight": h2h_weight, "matches": len(future),
                            "match_log_loss": metrics["blend_log_loss"], "match_brier": metrics["blend_brier"],
                            **position_metrics(counts / n_sim, points, actual_order, actual_standings)})
        LOG.info("Evaluated season %s, cutoff %s.", season, cutoff_round)
    return pd.DataFrame(reports), coverage


def run_ablation(*, competition="PD", tune_seasons, eval_seasons, cutoffs=(5, 10, 20, 30),
                 xg_grid=(0.0, 0.25, 0.5, 0.75, 1.0), h2h_grid=(0.0, 0.05, 0.1, 0.2, 0.3),
                 n_sim=2000, seed=7, prior_seasons=2, xi=0.003, lambda_reg=0.1, weights=None,
                 h2h_seasons=DEFAULT_H2H["seasons"], out_dir=Path("out/ablation"), cache=True):
    tune_seasons, eval_seasons = sorted(set(tune_seasons)), sorted(set(eval_seasons))
    if not tune_seasons or not eval_seasons or max(tune_seasons) >= min(eval_seasons):
        raise ValueError("Tuning seasons must all precede evaluation seasons.")
    if 0.0 not in xg_grid or 0.0 not in h2h_grid:
        raise ValueError("Grids must include 0 so the baseline is a candidate.")
    weights = weights or DEFAULT_WEIGHTS
    client = FootballDataClient(use_cache=cache) if os.getenv("FOOTBALL_DATA_API_KEY") else None
    span = max(eval_seasons) - min(tune_seasons)
    results = load_h2h_results(client, competition, max(eval_seasons) + 1, seasons=h2h_seasons + span, cache=cache)
    residuals = encounter_residuals(results, xi=xi, lambda_reg=lambda_reg)
    common = dict(prior_seasons=prior_seasons, xi=xi, lambda_reg=lambda_reg, residuals=residuals, weights=weights, cache=cache)
    grid = tune(client, competition, tune_seasons, cutoffs, xg_grid=xg_grid, h2h_grid=h2h_grid, **common)
    variants = choose_variants(grid)
    LOG.info("Frozen variants from tuning seasons: %s", variants)
    report, coverage = evaluate(client, competition, eval_seasons, cutoffs, variants, n_sim=n_sim, seed=seed, **common)
    summary = report.groupby("variant", sort=False)[METRICS].mean()
    summary.insert(0, "snapshots", report.groupby("variant", sort=False).size())
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    grid.to_csv(output / "tuning_grid.csv", index=False)
    report.to_csv(output / "metrics.csv", index=False)
    summary.to_csv(output / "summary.csv")
    metadata = {
        "competition": competition, "tune_seasons": tune_seasons, "eval_seasons": eval_seasons, "cutoff_rounds": list(cutoffs),
        "variants": {name: {"xg_weight": w, "h2h_weight": b} for name, (w, b) in variants.items()},
        "selection": "Lowest blend match log loss on tuning seasons; weights frozen before evaluation.",
        "n_sim": n_sim, "seed": seed, "prior_seasons": prior_seasons, "xi": xi, "lambda_reg": lambda_reg, "weights": weights,
        "h2h": {**DEFAULT_H2H, "seasons": h2h_seasons, "refit_days": 28, "baseline_window_days": 730},
        "xg_provider": "understat", "xg_coverage": {str(season): value for season, value in sorted(coverage.items())},
        "xg_availability": "Retrospective: Understat xG is assumed published by the end of each match's UTC day; "
                           "historical publication times are not reconstructed.",
        "odds": "Excluded; variants are compared on team models only, so market information is not controlled for.",
        "independence": "Cutoffs within a season overlap; snapshots are not independent observations.",
    }
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2, default=str) + "\n")
    return summary, report, grid, variants


def _floats(values):
    return tuple(float(value) for value in values)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tune xG/head-to-head weights on earlier seasons, then compare baseline, xG, H2H and both on later seasons.")
    parser.add_argument("--competition", default="PD", choices=["PD", "PL", "BL1", "SA", "FL1"])
    parser.add_argument("--tune-seasons", nargs="+", type=int, required=True)
    parser.add_argument("--eval-seasons", nargs="+", type=int, required=True)
    parser.add_argument("--cutoffs", nargs="+", type=int, default=[5, 10, 20, 30])
    parser.add_argument("--xg-grid", nargs="+", type=float, default=[0.0, 0.25, 0.5, 0.75, 1.0])
    parser.add_argument("--h2h-grid", nargs="+", type=float, default=[0.0, 0.05, 0.1, 0.2, 0.3])
    parser.add_argument("--n-sim", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--prior-seasons", type=int, default=2)
    parser.add_argument("--h2h-seasons", type=int, default=DEFAULT_H2H["seasons"])
    parser.add_argument("--out-dir", type=Path, default=Path("out/ablation"))
    parser.add_argument("--cache", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args(argv)
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    summary, _, _, variants = run_ablation(
        competition=args.competition, tune_seasons=args.tune_seasons, eval_seasons=args.eval_seasons,
        cutoffs=args.cutoffs, xg_grid=_floats(args.xg_grid), h2h_grid=_floats(args.h2h_grid), n_sim=args.n_sim,
        seed=args.seed, prior_seasons=args.prior_seasons, h2h_seasons=args.h2h_seasons, out_dir=args.out_dir, cache=args.cache)
    print("Frozen weights:", {name: {"xg": w, "h2h": b} for name, (w, b) in variants.items()})
    print(summary.to_string(float_format=lambda value: f"{value:.4f}"))
    print(f"Wrote tuning grid, metrics and summary to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
