import argparse
import hashlib
import json
import logging
from pathlib import Path
import shutil

import pandas as pd
from dotenv import load_dotenv

from standing_prediction.defaults import CALIBRATION_VERSION, DEFAULT_FIT, DEFAULT_WEIGHTS, DEFAULT_XG_SCALE, DEFAULT_XG_WEIGHT
from standing_prediction.utils import normalize_team


def run_forecast(*, season=None, as_of=None, n_sim=10000, seed=7, out_dir="out",
                 cache=True, odds_snapshot=None, inputs=None, offset_ridge=4.0, sensitivity=True):
    from champions_league.data import load_inputs
    from champions_league.coefficients import fetch_coefficients
    from champions_league.report import write_report
    from champions_league.strengths import fit_strengths
    from champions_league.tournament import simulate_tournament

    if n_sim < 1:
        raise ValueError("n_sim must be positive.")
    origin = pd.Timestamp(as_of) if as_of is not None else pd.Timestamp.now(tz="UTC")
    origin = origin.tz_localize("UTC") if origin.tzinfo is None else origin.tz_convert("UTC")
    season = season if season is not None else origin.year - (origin.month < 7)
    inputs = inputs or load_inputs(season=season, as_of=origin, prior_seasons=DEFAULT_FIT["prior_seasons"], cache=cache)
    teams = inputs.standings["team"].tolist()
    coefficients, coefficient_metadata = fetch_coefficients(season, teams, cache=cache)
    coefficients = coefficients if coefficient_metadata["complete"] else None
    logging.info("Fitting %s dated results across %s leagues.", len(inputs.history), len(set(inputs.team_leagues.values())))
    model = fit_strengths(inputs.history, teams=teams, team_leagues=inputs.team_leagues, as_of=origin,
                          offset_ridge=offset_ridge)
    odds = pd.read_csv(odds_snapshot) if odds_snapshot else None
    if odds is not None:
        from champions_league.identities import canonical_team
        for side in ("home", "away"):
            source = f"{side}_team" if f"{side}_team" in odds else f"{side}_norm"
            if source in odds:
                odds[f"{side}_norm"] = odds[source].map(lambda name: normalize_team(canonical_team(name)))
    result = simulate_tournament(inputs.fixtures, inputs.standings, model, n_sim=n_sim, seed=seed,
                                 season=season, odds=odds, as_of=origin, coefficients=coefficients)
    result.metadata.update({
        "competition": "CL", "season": season, "as_of": origin.isoformat(),
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(), "n_sim": n_sim, "seed": seed,
        "weight_calibration_version": CALIBRATION_VERSION, "weights": DEFAULT_WEIGHTS,
        "xg_weight": DEFAULT_XG_WEIGHT, "xg_scale": DEFAULT_XG_SCALE, "h2h_weight": 0, "fit_settings": DEFAULT_FIT,
        "data": inputs.metadata, "strengths": model.metadata,
        "coefficients": coefficient_metadata,
        "implementation_version": "football-champions-league/0.1.0",
        "code_fingerprint": hashlib.sha256(b"".join(path.read_bytes() for path in sorted(Path(__file__).parent.glob("*.py")))).hexdigest()[:16],
        "uncertainty": "Probabilities condition on fitted strengths; Monte Carlo errors exclude model, data and squad uncertainty.",
    })
    sparse = set(model.metadata["graph"]["sparse_leagues"]) & {inputs.team_leagues[t] for t in teams}
    if sensitivity and sparse:
        title_sensitivity = {str(offset_ridge): result.summary["title_pct"].to_dict()}
        for ridge in (1.0, 16.0):
            alternate = fit_strengths(inputs.history, teams=teams, team_leagues=inputs.team_leagues,
                                      as_of=origin, offset_ridge=ridge)
            forecast = simulate_tournament(inputs.fixtures, inputs.standings, alternate, n_sim=n_sim,
                                           seed=seed, season=season, odds=odds, as_of=origin, coefficients=coefficients)
            title_sensitivity[str(ridge)] = forecast.summary["title_pct"].to_dict()
        result.metadata["prior_sensitivity"] = {"sparse_leagues": sorted(sparse), "title_pct_by_offset_ridge": title_sensitivity,
            "interpretation": "Sensitivity to league-offset shrinkage, including Monte Carlo noise; not a confidence interval."}
        alternate_titles = pd.DataFrame(title_sensitivity)
        result.summary["prior_title_min_pct"] = alternate_titles.min(axis=1)
        result.summary["prior_title_max_pct"] = alternate_titles.max(axis=1)
    write_report(result, inputs, out_dir)
    out_dir = Path(out_dir)
    save_match_forecasts(inputs, model, out_dir, origin=origin, season=season, offset_ridge=offset_ridge)
    inputs.fixtures.to_csv(out_dir / "cl_matches_snapshot.csv", index=False)
    inputs.standings.to_csv(out_dir / "cl_standings_snapshot.csv", index=False)
    inputs.history.to_csv(out_dir / "cl_history_snapshot.csv", index=False)
    inputs.coverage.to_csv(out_dir / "cl_coverage.csv", index=False)
    (out_dir / "cl_identities.json").write_text(json.dumps(inputs.team_leagues, indent=2) + "\n")
    if odds is not None:
        odds.to_csv(out_dir / "cl_odds_snapshot.csv", index=False)
    else:
        (out_dir / "cl_odds_snapshot.csv").unlink(missing_ok=True)
    archive = out_dir / "snapshots" / "cl" / str(season) / pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%S%fZ")
    archive.mkdir(parents=True, exist_ok=True)
    for path in out_dir.glob("cl_*"):
        if path.is_file():
            shutil.copy2(path, archive / path.name)
    return result


def save_match_forecasts(inputs, model, out_dir, *, origin, season, offset_ridge=4.0):
    """Every known UCL fixture's 90-minute forecast, with played matches forecast as of their match day."""
    from champions_league.match_forecasts import match_forecasts
    from standing_prediction.match_forecasts import write_match_forecasts
    from standing_prediction.predict_positions import PLAYED_FORECAST_RULE

    records = match_forecasts(inputs, model, origin=origin, offset_ridge=offset_ridge)
    write_match_forecasts(out_dir / "cl_match_forecasts.json", records, {
        "competition": "CL", "season": season, "generated_at": origin.isoformat(), "weights": DEFAULT_WEIGHTS,
        "xg_weight": DEFAULT_XG_WEIGHT, "xg_scale": DEFAULT_XG_SCALE, "odds": False, "weight_calibration_version": CALIBRATION_VERSION,
        "played_forecast_rule": PLAYED_FORECAST_RULE, "score_rule": "Scores and forecasts cover 90 minutes.",
        "display_names": inputs.metadata["display_names"],
    })


def main(argv=None):
    parser = argparse.ArgumentParser(description="Forecast Champions League standings and the knockout bracket.")
    parser.add_argument("--season", type=int, help="Season start year; defaults to the current July-based season.")
    parser.add_argument("--as-of", help="UTC forecast origin (ISO timestamp); all results must precede it.")
    parser.add_argument("--n-sim", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out-dir", type=Path, default=Path("out"))
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--odds-snapshot", type=Path, help="Optional timestamped fixture odds CSV; default is no odds.")
    parser.add_argument("--evaluate", action="store_true", help="Replay 2024/25 and 2025/26 origins and compare international match forecasts.")
    args = parser.parse_args(argv)
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if args.evaluate:
        from champions_league.evaluate import evaluate
        evaluate(n_sim=args.n_sim, seed=args.seed, out_dir=args.out_dir, cache=not args.no_cache)
        return
    result = run_forecast(season=args.season, as_of=args.as_of, n_sim=args.n_sim, seed=args.seed,
                          out_dir=args.out_dir, cache=not args.no_cache, odds_snapshot=args.odds_snapshot)
    favorite = result.summary["title_pct"].idxmax()
    names = result.metadata["data"].get("display_names", {})
    print(f"Title favorite: {names.get(favorite, favorite)} ({result.summary.loc[favorite, 'title_pct']:.2f}%).")
    print(f"Report: {(args.out_dir / 'cl_forecast.html').resolve()}")


if __name__ == "__main__":
    main()
