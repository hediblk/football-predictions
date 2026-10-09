from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from html import escape
import json
import logging
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
from dotenv import load_dotenv

from standing_prediction.calibration import train_outcome_calibrator
from standing_prediction.data import FootballDataClient, fetch_matches, fetch_standings, validate_schedule
from standing_prediction.dixon_coles import fit_dixon_coles
from standing_prediction.elo import fit_elo
from standing_prediction.ensemble import blend_probabilities
from standing_prediction.odds import (
    COMPETITION_TO_FOOTBALL_DATA_UK_LEAGUE,
    fetch_football_data_uk_matches,
    fetch_football_data_uk_probs,
    fetch_the_odds_api_h2h_probs,
    match_odds,
)
from standing_prediction.h2h import encounter_residuals, h2h_shifts, pair_effects
from standing_prediction.simulate import FixtureSimulationSpec, simulate_season_scores
from standing_prediction.xg import XG_COLUMNS, blend_xg_strengths, fit_xg_strengths, load_season_xg
from standing_prediction.utils import normalize_team


LOG = logging.getLogger(__name__)
DEFAULT_WEIGHTS = {"main": 0.35, "odds": 0.55, "elo": 0.10}
DEFAULT_H2H = {"seasons": 6, "half_life_days": 730, "shrinkage": 4.0}
COMPETITION_TO_THE_ODDS_API_SPORT = {
    "PD": "soccer_spain_la_liga", "PL": "soccer_epl", "BL1": "soccer_germany_bundesliga",
    "SA": "soccer_italy_serie_a", "FL1": "soccer_france_ligue_one",
}


@dataclass
class Forecast:
    probabilities: pd.DataFrame
    summary: pd.DataFrame
    standings: pd.DataFrame
    metadata: dict


def main(argv=None):
    parser = argparse.ArgumentParser(description="Predict final league positions from a dated season snapshot.")
    parser.add_argument("--competition", default="PD", choices=list(COMPETITION_TO_THE_ODDS_API_SPORT))
    parser.add_argument("--season", type=int, help="Season start year; defaults to the current European season")
    parser.add_argument("--n-sim", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-goals", type=int, default=10)
    parser.add_argument("--xi", type=float, default=0.003)
    parser.add_argument("--lambda-reg", type=float, default=0.1)
    parser.add_argument("--prior-seasons", type=int, default=2)
    parser.add_argument("--use-odds", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--odds-provider", choices=["the_odds_api", "football_data_uk", "none"], default="the_odds_api")
    parser.add_argument("--odds-days", type=int, default=180)
    parser.add_argument("--odds-snapshot", type=Path, help="CSV with timestamped odds saved by an earlier run")
    parser.add_argument("--out-dir", type=Path, default=Path("out"))
    parser.add_argument("--weights", default="main=0.35,odds=0.55,elo=0.10")
    parser.add_argument("--calibrate", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--calibration-seasons", nargs="+", type=int)
    parser.add_argument("--calibration-cutoffs", "--calibration-cutoff-matchday", nargs="+", type=int, default=[5, 10, 20, 30])
    parser.add_argument("--xg-weight", type=float, default=0.0, help="Weight of Understat xG strengths in log goal rates (0 disables)")
    parser.add_argument("--h2h-weight", type=float, default=0.0, help="Log-rate shift per goal of shrunk head-to-head residual (0 disables)")
    parser.add_argument("--h2h-seasons", type=int, default=DEFAULT_H2H["seasons"])
    parser.add_argument("--cache", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    load_dotenv()
    options = vars(args)
    options["weights"] = _parse_weights(options["weights"])
    result = run_prediction(**options)
    print(result.summary.to_string(float_format=lambda x: f"{x:.2f}"))
    print(f"Wrote forecast files to {args.out_dir}")
    return 0


def load_season_results(client, competition, season, *, cache=True, xg=False):
    league = COMPETITION_TO_FOOTBALL_DATA_UK_LEAGUE.get(competition)
    matches = None
    if league:
        try:
            matches = fetch_football_data_uk_matches(league_code=league, season_start_year=season, use_cache=cache)
        except (ValueError, OSError, RuntimeError) as exc:
            LOG.warning("Historical CSV unavailable for season %s (%s).", season, type(exc).__name__)
    if matches is None:
        if client is None:
            raise ValueError(f"Cannot load season {season}; no football-data.org client is configured.")
        matches = fetch_matches(client, competition=competition, season=season, status="FINISHED")
    return load_season_xg(matches, competition=competition, season=season, cache=cache) if xg else matches


def load_history(client, competition, season, teams, *, prior_seasons=2, cache=True, xg=False):
    frames = []
    loaded = []
    coverage = {}
    names = {normalize_team(team): team for team in teams}
    for year in range(season - prior_seasons, season):
        try:
            matches = load_season_results(client, competition, year, cache=cache, xg=xg).copy()
        except (ValueError, OSError, RuntimeError) as exc:
            LOG.warning("Prior season %s unavailable (%s); continuing with available history.", year, type(exc).__name__)
            continue
        if "xg_coverage" in matches.attrs:
            coverage[year] = matches.attrs["xg_coverage"]
        for column in ["homeTeam", "awayTeam"]:
            matches[column] = matches[column].map(lambda team: names.get(normalize_team(team), team))
        frames.append(matches)
        loaded.append(year)
    history = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    history.attrs["seasons"] = loaded
    history.attrs["xg_coverage"] = coverage
    return history


def load_h2h_results(client, competition, season, *, seasons=DEFAULT_H2H["seasons"], warmup_seasons=2, cache=True):
    """Results for head-to-head residuals: `seasons` of meetings plus warm-up seasons for prior-only baselines."""
    frames = []
    for year in range(season - seasons - warmup_seasons, season):
        try:
            frames.append(load_season_results(client, competition, year, cache=cache))
        except (ValueError, OSError, RuntimeError) as exc:
            LOG.warning("Head-to-head season %s unavailable (%s).", year, type(exc).__name__)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fit_model_components(finished, *, teams, history=None, reference_date=None, xi=0.003, lambda_reg=0.1,
                         xg=False, h2h_residuals=None, h2h_half_life=DEFAULT_H2H["half_life_days"],
                         h2h_shrinkage=DEFAULT_H2H["shrinkage"]):
    """Fit goal, Elo and optional xG/head-to-head inputs once; weights are applied separately."""
    frames = [frame for frame in [history, finished] if frame is not None and not frame.empty]
    if not frames:
        raise ValueError("No results available: load prior seasons before forecasting an unplayed season.")
    matches = pd.concat(frames, ignore_index=True)
    matches["utcDate"] = pd.to_datetime(matches["utcDate"], utc=True)
    if reference_date is not None:
        matches = matches[matches["utcDate"] < pd.to_datetime(reference_date, utc=True)]
    matches = matches.drop_duplicates(["utcDate", "homeTeam", "awayTeam"])
    dc = fit_dixon_coles(matches, teams=teams, reference_date=reference_date, xi=xi, lambda_reg=lambda_reg)
    elo = fit_elo(matches, teams=teams, reference_date=reference_date)
    xg_strengths = fit_xg_strengths(matches, reference_date=reference_date, xi=xi, lambda_reg=lambda_reg) if xg else None
    effects = None
    if h2h_residuals is not None:
        as_of = reference_date if reference_date is not None else matches["utcDate"].max() + pd.Timedelta(seconds=1)
        effects = pair_effects(h2h_residuals, as_of, half_life_days=h2h_half_life, shrinkage=h2h_shrinkage)
    return dc, elo, xg_strengths, effects


def adjust_goal_model(dc, *, teams, xg_strengths=None, xg_weight=0.0, h2h_effects=None, h2h_weight=0.0):
    dc = blend_xg_strengths(dc, xg_strengths, xg_weight)
    shifts = h2h_shifts(teams, h2h_effects, h2h_weight)
    return replace(dc, pair_shift=shifts) if shifts else dc


def fit_prediction_models(finished, *, teams, history=None, reference_date=None, xi=0.003, lambda_reg=0.1,
                          xg_weight=0.0, h2h_weight=0.0, h2h_residuals=None,
                          h2h_half_life=DEFAULT_H2H["half_life_days"], h2h_shrinkage=DEFAULT_H2H["shrinkage"]):
    dc, elo, xg_strengths, effects = fit_model_components(
        finished, teams=teams, history=history, reference_date=reference_date, xi=xi, lambda_reg=lambda_reg,
        xg=xg_weight > 0, h2h_residuals=h2h_residuals if h2h_weight else None,
        h2h_half_life=h2h_half_life, h2h_shrinkage=h2h_shrinkage)
    dc = adjust_goal_model(dc, teams=teams, xg_strengths=xg_strengths, xg_weight=xg_weight,
                           h2h_effects=effects, h2h_weight=h2h_weight)
    return dc, elo


def run_prediction(*, competition="PD", season=None, n_sim=10000, seed=7, max_goals=10,
                   xi=0.003, lambda_reg=0.1, prior_seasons=2, use_odds=True,
                   odds_provider="the_odds_api", odds_days=180, odds_snapshot=None,
                   out_dir=Path("out"), weights=None, calibrate=False, calibration_seasons=None,
                   calibration_cutoffs=(5, 10, 20, 30), cache=True, client=None,
                   xg_weight=0.0, h2h_weight=0.0, h2h_seasons=DEFAULT_H2H["seasons"]):
    if n_sim < 1 or max_goals < 1 or prior_seasons < 0:
        raise ValueError("n_sim/max_goals must be positive; prior_seasons cannot be negative.")
    if not 0 <= xg_weight <= 1 or not np.isfinite(h2h_weight) or h2h_seasons < 1:
        raise ValueError("xg_weight must be in [0, 1], h2h_weight finite, and h2h_seasons positive.")
    season = _guess_season_start_year() if season is None else season
    client = client or FootballDataClient(use_cache=cache)
    standings = fetch_standings(client, competition=competition, season=season).sort_values("position").reset_index(drop=True)
    matches = fetch_matches(client, competition=competition, season=season, status=None)
    remaining = validate_schedule(matches, standings)
    finished = matches[matches["status"] == "FINISHED"].copy()
    # Retain current-season xG with every forecast for later prospective evaluation.
    finished = load_season_xg(finished, competition=competition, season=season, cache=cache)
    xg_coverage = {season: finished.attrs.get("xg_coverage")}
    matches[XG_COLUMNS] = finished[XG_COLUMNS]
    h2h_pairs = 0
    cutoff = pd.Timestamp.now(tz="UTC")
    teams = standings["team"].tolist()
    history = pd.DataFrame()
    odds, lookup, calibrator, years = None, {}, None, []
    if remaining.empty:
        counts = pd.DataFrame(0, index=teams, columns=range(1, len(teams) + 1))
        for row in standings.itertuples():
            counts.loc[row.team, int(row.position)] = n_sim
        points = np.broadcast_to(standings["points"].to_numpy(), (n_sim, len(teams))).copy()
        LOG.info("Season is complete; using the official final standings.")
    else:
        history = load_history(client, competition, season, teams, prior_seasons=prior_seasons, cache=cache, xg=xg_weight > 0)
        xg_coverage.update(history.attrs.get("xg_coverage", {}))
        residuals = None
        if h2h_weight:
            h2h_results = pd.concat([load_h2h_results(client, competition, season, seasons=h2h_seasons, cache=cache), finished],
                                    ignore_index=True)
            residuals = encounter_residuals(h2h_results, xi=xi, lambda_reg=lambda_reg)
        odds = None
        if use_odds and not remaining.empty:
            if odds_snapshot is not None:
                odds = pd.read_csv(odds_snapshot)
            elif odds_provider != "none":
                odds = _load_odds(competition=competition, season=season, provider=odds_provider, days=odds_days)
        cutoff = pd.Timestamp.now(tz="UTC")
        dc, elo = fit_prediction_models(finished, teams=teams, history=history, reference_date=cutoff, xi=xi,
                                        lambda_reg=lambda_reg, xg_weight=xg_weight, h2h_weight=h2h_weight,
                                        h2h_residuals=residuals)
        h2h_pairs = len(dc.pair_shift)
        lookup = match_odds(remaining, odds, as_of=cutoff) if odds is not None else {}
        LOG.info("Odds coverage: %s/%s remaining fixtures.", len(lookup), len(remaining))

        calibrator = None
        if calibrate:
            years = calibration_seasons or list(range(season - 3, season))
            if any(year >= season for year in years):
                raise ValueError("Calibration seasons must precede the forecast season.")
            calibrator = _train_calibrator(client, competition=competition, seasons=years,
                                          cutoffs=calibration_cutoffs, prior_seasons=prior_seasons,
                                          xi=xi, lambda_reg=lambda_reg, cache=cache, weights=weights)
        specs = build_fixture_specs(remaining, dc=dc, elo=elo, odds=odds, as_of=cutoff,
                                   max_goals=max_goals, weights=weights or DEFAULT_WEIGHTS, calibrator=calibrator)
        counts, points = simulate_season_scores(specs, standings, n_sim=n_sim, seed=seed,
                                                played_matches=finished, competition=competition, return_details=True)
    probabilities = counts / n_sim * 100
    summary = forecast_summary(probabilities, points)
    metadata = {
        "competition": competition, "season": season, "generated_at": cutoff.isoformat(),
        "data_cutoff": finished["utcDate"].max().isoformat() if not finished.empty else None,
        "finished_fixtures": len(finished), "remaining_fixtures": len(remaining), "completed": remaining.empty,
        "odds_matched": len(lookup), "odds_requested": bool(use_odds),
        "odds_provider": "snapshot" if odds_snapshot else odds_provider if use_odds else "none",
        "prior_seasons": history.attrs.get("seasons", []), "n_sim": n_sim, "seed": seed,
        "max_goals": max_goals, "xi": xi, "lambda_reg": lambda_reg,
        "weights": weights or DEFAULT_WEIGHTS, "calibrated": calibrator is not None,
        "calibration_seasons": years if calibrate else [],
        "calibration_cutoffs": list(calibration_cutoffs) if calibrate else [],
        "xg_weight": xg_weight, "xg_provider": "understat", "xg_coverage": xg_coverage,
        "h2h_weight": h2h_weight, "h2h": {**DEFAULT_H2H, "seasons": h2h_seasons, "adjusted_fixtures": h2h_pairs} if h2h_weight else None,
        "tiebreak_fallback": "Random ordering only after modeled sporting criteria; fair-play and playoff matches are not modeled.",
        "uncertainty": "Point intervals reflect simulated match results, conditional on fitted team strengths.",
    }
    result = Forecast(probabilities, summary, standings, metadata)
    write_forecast(result, out_dir)
    matches.to_csv(Path(out_dir) / f"{competition.lower()}_matches_snapshot.csv", index=False)
    standings.to_csv(Path(out_dir) / f"{competition.lower()}_standings_snapshot.csv", index=False)
    if odds is not None and not odds.empty:
        path = Path(out_dir) / f"{competition.lower()}_odds_snapshot.csv"
        odds.to_csv(path, index=False)
    else:
        (Path(out_dir) / f"{competition.lower()}_odds_snapshot.csv").unlink(missing_ok=True)
    archive = Path(out_dir) / "snapshots" / competition.lower() / str(season) / cutoff.strftime("%Y%m%dT%H%M%S%fZ")
    archive.mkdir(parents=True, exist_ok=True)
    for artifact in Path(out_dir).glob(f"{competition.lower()}_*"):
        if artifact.is_file() and ("odds_snapshot" not in artifact.name or odds is not None and not odds.empty):
            shutil.copy2(artifact, archive / artifact.name)
    return result


def forecast_summary(probabilities, points):
    p = probabilities / 100
    n_teams = len(p)
    summary = pd.DataFrame(index=p.index)
    summary["expected_position"] = p.mul(np.arange(1, n_teams + 1), axis=1).sum(axis=1)
    summary["expected_points"] = points.mean(axis=0)
    summary["points_p10"] = np.quantile(points, 0.1, axis=0)
    summary["points_p90"] = np.quantile(points, 0.9, axis=0)
    events = {"title_pct": p.iloc[:, 0], "top_four_pct": p.iloc[:, :min(4, n_teams)].sum(axis=1),
              "bottom_three_pct": p.iloc[:, max(0, n_teams - 3):].sum(axis=1)}
    for name, event in events.items():
        event = event.clip(0, 1)
        summary[name] = 100 * event
        summary[name.replace("_pct", "_mc_se_pp")] = 100 * np.sqrt(event * (1 - event) / len(points))
    return summary.round(4)


def write_forecast(result, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = result.metadata["competition"].lower()
    result.probabilities.to_csv(out_dir / f"{prefix}_position_probs.csv", float_format="%.4f")
    result.summary.to_csv(out_dir / f"{prefix}_summary.csv", float_format="%.4f")
    (out_dir / f"{prefix}_metadata.json").write_text(json.dumps(result.metadata, indent=2) + "\n")
    _write_html(result.probabilities, standings=result.standings, path=out_dir / f"{prefix}_position_probs.html",
                summary=result.summary, metadata=result.metadata)


def build_fixture_specs(remaining, *, dc, elo, odds, max_goals, weights, calibrator=None, as_of=None):
    if max_goals < 1:
        raise ValueError("max_goals must be at least 1.")
    scorelines = _scoreline_grid(max_goals)
    masks = [scorelines[:, 0] > scorelines[:, 1], scorelines[:, 0] == scorelines[:, 1], scorelines[:, 0] < scorelines[:, 1]]
    lookup = match_odds(remaining, odds, as_of=as_of) if odds is not None else {}
    specs = []
    for row in remaining.itertuples():
        home, away = str(row.homeTeam), str(row.awayTeam)
        p_dc = dc.match_outcome_probs(home, away, max_goals=max_goals)
        p_elo = elo.predict_probs(home, away)
        p_odds = lookup.get((home, away))
        p = predict_outcome_probs(p_dc, p_elo, p_odds, weights=weights, calibrator=calibrator)
        _, matrix = dc.score_matrix(home, away, max_goals=max_goals)
        conditionals = tuple(_conditional_probs(matrix.reshape(-1), mask) for mask in masks)
        specs.append(FixtureSimulationSpec(home, away, *p, scorelines, conditionals))
    return specs


def predict_outcome_probs(p_dc, p_elo, p_odds=None, *, weights=None, calibrator=None):
    weights = weights or DEFAULT_WEIGHTS
    if calibrator is None:
        return blend_probabilities(p_dc, p_odds=p_odds, p_elo=p_elo, weights=weights)
    p = calibrator.predict_probs(p_dc=p_dc, p_elo=p_elo, p_book=p_odds)
    if p_odds is not None and calibrator.odds_model is None:
        # Timestamp-free historical data can calibrate team models, but cannot learn an odds blend.
        return blend_probabilities(p, p_odds=p_odds,
                                   weights={"main": weights.get("main", 0) + weights.get("elo", 0), "odds": weights.get("odds", 0)})
    return p


def _conditional_probs(p_flat, mask):
    probs = p_flat * mask
    total = probs.sum()
    if not np.isfinite(total) or total <= 0:
        raise ValueError("The score model assigned no finite mass to an outcome.")
    return probs / total


def _scoreline_grid(max_goals):
    home, away = np.meshgrid(np.arange(max_goals + 1), np.arange(max_goals + 1), indexing="ij")
    return np.column_stack([home.ravel(), away.ravel()])


def _parse_weights(spec):
    weights = dict(part.strip().split("=", 1) for part in spec.split(",") if part.strip())
    if set(weights) - set(DEFAULT_WEIGHTS):
        raise ValueError("Weights must use main, odds, and/or elo.")
    weights = {key: float(value) for key, value in weights.items()}
    if not weights or any(not np.isfinite(value) or value < 0 for value in weights.values()) or sum(weights.values()) <= 0:
        raise ValueError("Weights must be finite, nonnegative, and have a positive total.")
    return {key: weights.get(key, 0.0) for key in DEFAULT_WEIGHTS}


def _load_odds(*, competition, season, provider, days):
    try:
        if provider == "the_odds_api":
            return fetch_the_odds_api_h2h_probs(sport_key=COMPETITION_TO_THE_ODDS_API_SPORT[competition], days=days)
        if provider == "football_data_uk":
            LOG.warning("Historical CSV odds have no observation timestamps and cannot enter a dated forecast.")
            return fetch_football_data_uk_probs(league_code=COMPETITION_TO_FOOTBALL_DATA_UK_LEAGUE[competition], season_start_year=season)
    except (ValueError, OSError, RuntimeError) as exc:
        LOG.warning("Odds unavailable (%s); using team models. Check provider configuration and quota.", type(exc).__name__)
    return None


def _write_html(probs, *, standings, path, summary=None, metadata=None):
    probs = probs.reindex(standings["team"])
    summary = summary if summary is not None else pd.DataFrame(index=probs.index)
    meta = metadata or {}
    names = {"PD": "La Liga", "PL": "Premier League", "BL1": "Bundesliga", "SA": "Serie A", "FL1": "Ligue 1"}
    season = meta.get("season")
    season_label = f"{season}/{str(season + 1)[-2:]}" if season is not None else ""
    title = f"{names.get(meta.get('competition'), 'League')} {season_label} — final-position forecast"

    def date_label(value):
        return pd.to_datetime(value, utc=True).strftime("%Y-%m-%d %H:%M UTC") if value else "no completed matches"

    details = f"Generated {date_label(meta.get('generated_at'))} · Results through {date_label(meta.get('data_cutoff'))} · {meta.get('n_sim', 0):,} simulations" if meta else ""
    coverage = f"Odds: {meta.get('odds_matched', 0)}/{meta.get('remaining_fixtures', 0)} remaining fixtures. Top four and bottom three describe table positions; qualification/playoff rules can differ."
    shown = pd.DataFrame(index=summary.index)
    for column, label in [("title_pct", "Title"), ("top_four_pct", "Top four"), ("bottom_three_pct", "Bottom three")]:
        if column in summary:
            shown[label] = summary[column].map(lambda value: f"{value:.1f}%")
    for column, label in [("expected_position", "Avg. position"), ("expected_points", "Avg. points")]:
        if column in summary:
            shown[label] = summary[column]
    if "points_p10" in summary:
        shown["Points: 80% range"] = [f"{low:.0f}–{high:.0f}" for low, high in zip(summary["points_p10"], summary["points_p90"])]
    summary_html = shown.to_html(float_format=lambda value: f"{value:.2f}")
    heatmap = style_probabilities(probs).to_html()
    levels = pd.DataFrame([[0, 0.1, 0.5, 1, 2, 5, 10, 20, 50, 100]])
    legend = style_probabilities(levels).hide(axis="index").hide(axis="columns").to_html()
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title>
<style>body{{font:15px system-ui,sans-serif;margin:32px;color:#18332a;background:#f8faf8}}h1{{font-size:26px}}table{{border-collapse:collapse;background:white}}th,td{{padding:8px;border-bottom:1px solid #ddd;text-align:right;white-space:nowrap}}th:first-child{{text-align:left}}.scroll{{overflow:auto;margin:20px 0}}p{{max-width:1000px;line-height:1.5}}</style></head><body>
<h1>{escape(title)}</h1><div class="scroll">{heatmap}</div>
<p>Probability color scale: continuous, with more detail at low probabilities. Exact zeros are white.</p><div class="scroll">{legend}</div>
<p>{escape(details)}</p><p>{escape(coverage)}</p><div class="scroll">{summary_html}</div>
<p>Point intervals cover the 10th–90th simulated percentiles. The summary CSV includes Monte Carlo standard errors in percentage points; they measure simulation sampling error, not model error.</p>
<p>{escape(meta.get('uncertainty', ''))}</p><p>{escape(meta.get('tiebreak_fallback', ''))}</p></body></html>'''
    Path(path).write_text(html, encoding="utf-8")


def style_probabilities(probabilities):
    if len(probabilities) > 1:
        positions = probabilities.columns.to_numpy(dtype=float)
        order = pd.DataFrame({
            "most_likely": probabilities.idxmax(axis=1).astype(float),
            "expected": probabilities.mul(positions, axis=1).sum(axis=1) / 100,
        }).sort_values(["most_likely", "expected"], kind="stable").index
        probabilities = probabilities.loc[order]
    return (
        probabilities.style.format("{:.2f}%")
        .background_gradient(cmap="YlGnBu", gmap=np.power(probabilities / 100, 0.4), axis=None, vmin=0, vmax=1)
        .map(lambda value: "background-color: #fff; color: #64748b" if value == 0 else "")
    )


def _train_calibrator(client, *, competition, seasons, cutoffs, prior_seasons, xi, lambda_reg, cache=True, weights=None):
    from standing_prediction.backtest import snapshot_features
    frames = []
    for season in sorted(set(seasons)):
        matches = load_season_results(client, competition, season, cache=cache)
        teams = sorted(set(matches["homeTeam"]) | set(matches["awayTeam"]))
        history = load_history(client, competition, season, teams, prior_seasons=prior_seasons, cache=cache)
        for cutoff in cutoffs:
            frame, _, _, _ = snapshot_features(matches, season=season, competition=competition,
                                               cutoff_matchday=cutoff, history=history, xi=xi,
                                               lambda_reg=lambda_reg, weights=weights)
            if not frame.empty:
                frames.append(frame)
    if not frames:
        raise ValueError("Calibration requested, but no historical forecast rows were produced.")
    return train_outcome_calibrator(pd.concat(frames, ignore_index=True), use_odds_features=False)


def _guess_season_start_year():
    today = pd.Timestamp.now(tz="UTC")
    return today.year if today.month >= 7 else today.year - 1


if __name__ == "__main__":
    raise SystemExit(main())
