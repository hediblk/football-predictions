from __future__ import annotations

import argparse
import json
import logging
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Mapping, Tuple

import numpy as np
import pandas as pd

from forecast_calibration.dataset import CALIBRATION_LEAGUES, XG_COMPETITIONS, XG_GRID, XG_SCALE_GRID, dc_prefix, load_season
from forecast_calibration.fit import select_weights
from standing_prediction.backtest import position_metrics, snapshot_split
from standing_prediction.data import standings_from_matches
from standing_prediction.dixon_coles import DixonColesModel, outcome_probs_from_matrix, score_matrix_from_rates
from standing_prediction.predict_positions import build_fixture_specs, fit_model_components
from standing_prediction.simulate import rank_table, simulate_season_scores
from standing_prediction.xg import NPXG_COLUMNS, XG_COLUMNS, blend_xg_strengths, fit_xg_strengths

LOG = logging.getLogger(__name__)
# Pseudo-games of league-average penalty xG added to each team's decayed record; inf is the league mean for all.
SHRINKAGE_GRID = (5.0, 10.0, 20.0, 40.0, 80.0, 160.0, np.inf)
POSITIVE = [(w, s) for w in XG_GRID if w for s in XG_SCALE_GRID]
META = ["league", "season", "forecast_at", "utcDate", "homeTeam", "awayTeam", "y", "odds_source", "training_last_available_at",
        "training_matches", *(f"book_{c}" for c in "hda"), *(f"elo_{c}" for c in "hda"), *(f"dc_0_{c}" for c in "hda")]


@dataclass(frozen=True)
class RateShiftedModel(DixonColesModel):
    # Per-fixture log-rate shifts for the home and away sides, applied after the goal/xG blend.
    rate_shift: Mapping[Tuple[str, str], Tuple[float, float]] = field(default_factory=dict)

    def expected_goals(self, home, away):
        lambda_, mu_ = super().expected_goals(home, away)
        shift_home, shift_away = self.rate_shift.get((home, away), (0.0, 0.0))
        return lambda_ * float(np.exp(shift_home)), mu_ * float(np.exp(shift_away))


@dataclass(frozen=True)
class PenaltyRates:
    home_mean: float
    away_mean: float
    games: Mapping[str, float]
    scored: Mapping[str, float]
    conceded: Mapping[str, float]

    def relative(self, team, shrinkage):
        # Decayed penalty xG relative to the venue mean, shrunk toward 1 (the league mean).
        if not np.isfinite(shrinkage) or team not in self.games:
            return 1.0, 1.0
        n = self.games[team]
        return (self.scored[team] + shrinkage) / (n + shrinkage), (self.conceded[team] + shrinkage) / (n + shrinkage)

    def expected(self, home, away, shrinkage):
        (home_for, home_against), (away_for, away_against) = self.relative(home, shrinkage), self.relative(away, shrinkage)
        return self.home_mean * home_for * away_against, self.away_mean * away_for * home_against


def fit_penalty_rates(matches, *, reference_date, xi):
    data = matches.dropna(subset=[*XG_COLUMNS, *NPXG_COLUMNS])
    dates = pd.to_datetime(data["utcDate"], utc=True)
    data = data[dates < reference_date]
    weights = np.exp(-xi * (reference_date - dates[dates < reference_date]).dt.total_seconds().to_numpy() / 86400.0)
    home = (data["home_xg"] - data["home_npxg"]).clip(lower=0).to_numpy(dtype=float)
    away = (data["away_xg"] - data["away_npxg"]).clip(lower=0).to_numpy(dtype=float)
    home_mean, away_mean = np.average(home, weights=weights), np.average(away, weights=weights)
    frame = pd.concat([
        pd.DataFrame({"team": data["homeTeam"].to_numpy(), "w": weights, "scored": home / home_mean, "conceded": away / away_mean}),
        pd.DataFrame({"team": data["awayTeam"].to_numpy(), "w": weights, "scored": away / away_mean, "conceded": home / home_mean}),
    ])
    frame[["scored", "conceded"]] = frame[["scored", "conceded"]].mul(frame["w"], axis=0)
    totals = frame.groupby("team")[["w", "scored", "conceded"]].sum()
    return PenaltyRates(float(home_mean), float(away_mean), totals["w"].to_dict(), totals["scored"].to_dict(), totals["conceded"].to_dict())


def penalty_shift(strengths, rates, shrinkage, home, away):
    # Log-rate change from adding expected penalty xG to the npxG rate, relative to an average pairing.
    if strengths is None or home not in strengths.attack or away not in strengths.attack:
        return 0.0, 0.0
    pen_home, pen_away = rates.expected(home, away, shrinkage)
    base_home = strengths.attack[home] + strengths.defense[away]
    base_away = strengths.attack[away] + strengths.defense[home]
    level_home, level_away = strengths.intercept + strengths.home_advantage, strengths.intercept
    total_home = np.log(np.exp(level_home + base_home) + pen_home) - np.log(np.exp(level_home) + rates.home_mean)
    total_away = np.log(np.exp(level_away + base_away) + pen_away) - np.log(np.exp(level_away) + rates.away_mean)
    return float(total_home - base_home), float(total_away - base_away)


def shifted(model, strengths, rates, shrinkage, weight, scale, teams):
    shifts = {}
    for home in teams:
        for away in teams:
            if home != away:
                p_home, p_away = penalty_shift(strengths, rates, shrinkage, home, away)
                shifts[(home, away)] = (weight * scale * p_home, weight * scale * p_away)
    return RateShiftedModel(**{f.name: getattr(model, f.name) for f in fields(model)}, rate_shift=shifts)


def variant_name(shrinkage):
    return "pen_inf" if not np.isfinite(shrinkage) else f"pen_{shrinkage:g}"


def fit_origin(train, teams, cutoff, xi, lambda_reg):
    dc, elo, xg, _ = fit_model_components(train, teams=teams, reference_date=cutoff, xi=xi, lambda_reg=lambda_reg, xg=True)
    npxg = fit_xg_strengths(train.assign(home_xg=train["home_npxg"], away_xg=train["away_npxg"]),
                            reference_date=cutoff, xi=xi, lambda_reg=lambda_reg)
    return dc, elo, xg, npxg, fit_penalty_rates(train, reference_date=cutoff, xi=xi)


def load_history(league, season, prior_seasons):
    history = {year: load_season(league, year, npxg=True) for year in range(max(2014, season - prior_seasons), season + 1)}
    prior = pd.concat(history.values(), ignore_index=True)
    return history[season], prior


def build_part(league, season, out_dir, xi=0.003, lambda_reg=2.0, prior_seasons=2):
    path = Path(out_dir) / f"{league}_{season}.parquet"
    if path.exists():
        return str(path)
    matches, prior = load_history(league, season, prior_seasons)
    teams = sorted(set(matches["homeTeam"]) | set(matches["awayTeam"]))
    rows = []
    for cutoff, future in matches.groupby("forecast_at", sort=True):
        train = prior[(prior["available_at"] <= cutoff) & (prior["utcDate"] < cutoff)]
        dc, elo, xg, npxg, rates = fit_origin(train, teams, cutoff, xi, lambda_reg)
        models = {"dc_0": dc}
        for w, s in POSITIVE:
            models[f"xg_{dc_prefix(w, s)}"] = blend_xg_strengths(dc, xg, w, s)
            models[f"npxg_{dc_prefix(w, s)}"] = blend_xg_strengths(dc, npxg, w, s)
        for match in future.itertuples(index=False):
            home, away = match.homeTeam, match.awayTeam
            row = {"league": league, "season": season, "forecast_at": cutoff.isoformat(), "utcDate": match.utcDate.isoformat(),
                   "training_last_available_at": train["available_at"].max().isoformat(), "training_matches": len(train),
                   "homeTeam": home, "awayTeam": away, "odds_source": match.odds_source,
                   "y": 0 if match.homeGoals > match.awayGoals else 1 if match.homeGoals == match.awayGoals else 2,
                   "pen_home": match.home_xg - match.home_npxg, "pen_away": match.away_xg - match.away_npxg}
            for c in "hda":
                row[f"book_{c}"] = getattr(match, f"book_{c}")
            row.update({f"elo_{c}": p for c, p in zip("hda", elo.predict_probs(home, away))})
            for name, model in models.items():
                row.update({f"{name}_{c}": p for c, p in zip("hda", model.match_outcome_probs(home, away))})
            for k in SHRINKAGE_GRID:
                name = variant_name(k)
                row[f"{name}_expected_home"], row[f"{name}_expected_away"] = rates.expected(home, away, k)
                p_home, p_away = penalty_shift(npxg, rates, k, home, away)
                for w, s in POSITIVE:
                    base = models[f"npxg_{dc_prefix(w, s)}"]
                    lambda_, mu_ = base.expected_goals(home, away)
                    _, matrix = score_matrix_from_rates(lambda_ * np.exp(w * s * p_home), mu_ * np.exp(w * s * p_away), base.rho)
                    row.update({f"{name}_{dc_prefix(w, s)}_{c}": p for c, p in zip("hda", outcome_probs_from_matrix(matrix))})
            rows.append(row)
    pd.DataFrame(rows).to_parquet(path, index=False)
    LOG.info("Built %s/%s: %s matches.", league, season, len(rows))
    return str(path)


def join_checks(leagues, seasons):
    rows = []
    for league in leagues:
        for season in range(max(2014, min(seasons) - 2), max(seasons) + 1):
            matches = load_season(league, season, npxg=True)
            pen = pd.concat([matches["home_xg"] - matches["home_npxg"], matches["away_xg"] - matches["away_npxg"]]).dropna()
            rows.append({"league": league, "season": season, "results": len(matches), **matches.attrs["npxg_join"],
                         "xg_attached": int(matches["home_xg"].notna().sum()), "npxg_attached": int(matches["home_npxg"].notna().sum()),
                         "penalty_xg_per_team_game": pen.mean(), "team_games_with_penalty_xg": float((pen > 0.01).mean())})
    return pd.DataFrame(rows)


def variant_frame(data, variant):
    if variant == "goals":
        return data[META].copy()
    columns = {c: c[len(variant) + 1:] for c in data.columns if c.startswith(f"{variant}_dc_")}
    return pd.concat([data[META], data[list(columns)].rename(columns=columns)], axis=1)


def penalty_fits(train):
    return [{"variant": variant_name(k), "shrinkage": k, **select_weights(variant_frame(train, variant_name(k)), XG_GRID, XG_SCALE_GRID)[0]}
            for k in SHRINKAGE_GRID]


def select_variant(train, variant):
    if variant == "pen":
        return min(penalty_fits(train), key=lambda fit: fit["metrics"]["objective"])
    best, _ = select_weights(variant_frame(train, variant), [0.0] if variant == "goals" else XG_GRID, XG_SCALE_GRID)
    return {"variant": variant, **best}


def no_odds_probs(frame, fitted):
    prefix = dc_prefix(fitted["xg_weight"], fitted["xg_scale"])
    dc = np.log(np.clip(frame[[f"{prefix}_{c}" for c in "hda"]].to_numpy(dtype=float), 1e-12, 1))
    elo = np.log(np.clip(frame[[f"elo_{c}" for c in "hda"]].to_numpy(dtype=float), 1e-12, 1))
    share = fitted["no_odds_weights"]["main"]
    logits = share * dc + (1 - share) * elo
    p = np.exp(logits - logits.max(axis=1, keepdims=True))
    return p / p.sum(axis=1, keepdims=True)


def match_scores(p, y):
    actual = np.eye(3)[y]
    cumulative = np.cumsum(p - actual, axis=1)[:, :2]
    return {"log_loss": -np.log(np.clip(p[np.arange(len(y)), y], 1e-12, 1)), "brier": np.square(p - actual).sum(axis=1),
            "rps": np.square(cumulative).sum(axis=1) / 2}


def scored_matches(data, fits):
    out = data[["league", "season", "forecast_at", "homeTeam", "awayTeam"]].copy()
    y = data["y"].to_numpy(dtype=int)
    for name, fitted in fits.items():
        frame = variant_frame(data, fitted["variant"])
        for metric, values in match_scores(no_odds_probs(frame, fitted), y).items():
            out[f"{name}_{metric}"] = values
    return out


def paired(scores, names, baseline="xg", metrics=("log_loss", "brier", "rps")):
    counts = scores.groupby(["league", "season"])["league"].transform("size").to_numpy(dtype=float)
    weights = 1 / counts
    weights /= weights.sum()
    clusters = pd.factorize(scores["league"] + "|" + scores["forecast_at"])[0]
    groups = clusters.max() + 1
    result = {"matches": len(scores), "clusters": int(groups)}
    for metric in metrics:
        base = scores[f"{baseline}_{metric}"].to_numpy()
        for name in names:
            values = scores[f"{name}_{metric}"].to_numpy()
            result[f"{name}_{metric}"] = float(weights @ values)
            if name == baseline:
                continue
            difference = values - base
            mean = weights @ difference
            totals = np.bincount(clusters, weights * (difference - mean), groups)
            result[f"{name}_minus_{baseline}_{metric}"] = float(mean)
            result[f"{name}_minus_{baseline}_{metric}_se"] = float(np.sqrt(groups / (groups - 1) * np.square(totals).sum()))
    return result


def breakdown(scores, names):
    rows = [{"league": "all", "season": "all", **paired(scores, names)}]
    for league, part in scores.groupby("league"):
        rows.append({"league": league, "season": "all", **paired(part, names)})
    for season, part in scores.groupby("season"):
        rows.append({"league": "all", "season": season, **paired(part, names)})
    for (league, season), part in scores.groupby(["league", "season"]):
        rows.append({"league": league, "season": season, **paired(part, names)})
    return pd.DataFrame(rows)


def describe(fit):
    return {key: fit.get(key) for key in ("variant", "shrinkage", "xg_weight", "xg_scale", "no_odds_weights")} | {
        "training_objective": fit["metrics"]["objective"], "training_no_odds_log_loss": fit["metrics"]["no_odds_log_loss"]}


def penalty_check(data, held_out):
    rows = []
    for k in SHRINKAGE_GRID:
        name = variant_name(k)
        for label, part in (("training", data[~data["season"].isin(held_out)]), ("held_out", data[data["season"].isin(held_out)])):
            part = part.dropna(subset=["pen_home", "pen_away"])
            predicted = np.concatenate([part[f"{name}_expected_home"], part[f"{name}_expected_away"]])
            actual = np.concatenate([part["pen_home"], part["pen_away"]])
            rows.append({"shrinkage": k, "seasons": label, "team_games": len(actual), "mse_x1000": 1000 * np.mean(np.square(predicted - actual)),
                         "predicted_sd": predicted.std(), "correlation": np.corrcoef(predicted, actual)[0, 1]})
    return pd.DataFrame(rows)


def evaluate(data, out_dir, holdout_seasons=2):
    seasons = sorted(data["season"].unique())
    held_out = seasons[-holdout_seasons:]
    train = data[~data["season"].isin(held_out)]
    shrinkage_fits = penalty_fits(train)
    fits = {name: select_variant(train, name) for name in ("goals", "xg", "npxg")}
    fits["pen"] = min(shrinkage_fits, key=lambda fit: fit["metrics"]["objective"])
    names = list(fits)
    holdout = breakdown(scored_matches(data[data["season"].isin(held_out)], fits), names)
    expanding_scores, expanding_fits = [], []
    for season in seasons[2:]:
        prior = data[data["season"] < season]
        season_fits = {name: select_variant(prior, name) for name in ("xg", "npxg", "pen")}
        expanding_fits.extend({"season": season, **describe(fit)} for fit in season_fits.values())
        expanding_scores.append(scored_matches(data[data["season"] == season], season_fits))
    expanding = breakdown(pd.concat(expanding_scores, ignore_index=True), ["xg", "npxg", "pen"])
    holdout.to_csv(out_dir / "holdout_metrics.csv", index=False)
    expanding.to_csv(out_dir / "expanding_metrics.csv", index=False)
    pd.DataFrame(expanding_fits).to_csv(out_dir / "expanding_selection.csv", index=False)
    checks = penalty_check(data, held_out)
    checks.to_csv(out_dir / "penalty_rate_check.csv", index=False)
    report = {"training_seasons": [int(s) for s in seasons[:-holdout_seasons]], "held_out_seasons": [int(s) for s in held_out],
              "selection": {name: describe(fit) for name, fit in fits.items()},
              "all_shrinkage": [describe(fit) for fit in shrinkage_fits],
              "held_out": holdout.iloc[0].to_dict()}
    (out_dir / "selection.json").write_text(json.dumps(report, indent=2, default=float) + "\n")
    return report


def replay_part(league, season, fits, cutoffs, n_sim, seed, xi=0.003, lambda_reg=2.0, prior_seasons=2):
    competition = XG_COMPETITIONS[league]
    matches, prior = load_history(league, season, prior_seasons)
    teams = sorted(set(matches["homeTeam"]) | set(matches["awayTeam"]))
    actual_standings = standings_from_matches(matches, teams=teams, competition=competition)
    actual_order = rank_table(actual_standings, matches, competition=competition)
    rows = []
    for cutoff_round in cutoffs:
        split = snapshot_split(matches, cutoff_round)
        if split is None:
            continue
        _, cutoff, played, future = split
        train = prior[prior["utcDate"] < cutoff]
        standings = standings_from_matches(played, teams=teams, competition=competition)
        dc, elo, xg, npxg, rates = fit_origin(train, teams, cutoff, xi, lambda_reg)
        for name, fit in fits.items():
            w, s = fit["xg_weight"], fit["xg_scale"]
            if name == "xg":
                model = blend_xg_strengths(dc, xg, w, s)
            elif name == "npxg":
                model = blend_xg_strengths(dc, npxg, w, s)
            else:
                model = shifted(blend_xg_strengths(dc, npxg, w, s), npxg, rates, fit["shrinkage"], w, s, teams)
            share = fit["no_odds_weights"]["main"]
            specs = build_fixture_specs(future, dc=model, elo=elo, odds=None, max_goals=10,
                                        weights={"main": share, "odds": 0.0, "elo": 1 - share})
            counts, points = simulate_season_scores(specs, standings, n_sim=n_sim, seed=seed, competition=competition,
                                                    played_matches=played, return_details=True)
            p = counts / n_sim
            rank = np.array([actual_order.index(team) + 1 for team in p.index])
            title, top_four = p.to_numpy()[:, 0], p.to_numpy()[:, :4].sum(axis=1)
            floor = 0.5 / n_sim
            rows.append({"league": league, "season": season, "cutoff_round": cutoff_round, "forecast_at": cutoff.isoformat(),
                         "variant": name, "fixtures": len(future),
                         "title_log_loss": float(-np.log(np.clip(title[rank == 1][0], floor, 1))),
                         "top_four_log_loss": float(-np.mean(np.where(rank <= 4, np.log(np.clip(top_four, floor, 1)),
                                                                      np.log(np.clip(1 - top_four, floor, 1))))),
                         **position_metrics(p, points, actual_order, actual_standings)})
    LOG.info("Replayed %s/%s.", league, season)
    return rows


def replay(out_dir, fits, leagues, seasons, cutoffs, n_sim, seed, workers, held_out):
    with ProcessPoolExecutor(workers) as pool:
        jobs = [pool.submit(replay_part, league, season, fits, cutoffs, n_sim, seed) for league in leagues for season in seasons]
        snapshots = pd.DataFrame([row for job in jobs for row in job.result()])
    snapshots.to_csv(out_dir / "replay_snapshots.csv", index=False)
    metrics = ["title_log_loss", "top_four_log_loss", "title_brier", "top_four_brier", "position_rps", "expected_points_mae"]
    rows = []
    for label, part in (("all", snapshots), ("held_out", snapshots[snapshots["season"].isin(held_out)])):
        wide = part.pivot_table(index=["league", "season", "cutoff_round"], columns="variant", values=metrics)
        for metric in metrics:
            row = {"seasons": label, "metric": metric, "snapshots": len(wide)}
            for name in fits:
                row[name] = wide[(metric, name)].mean()
                if name != "xg":
                    difference = (wide[(metric, name)] - wide[(metric, "xg")]).groupby(level=["league", "season"]).mean()
                    row[f"{name}_minus_xg"] = difference.mean()
                    row[f"{name}_minus_xg_se"] = difference.std(ddof=1) / np.sqrt(len(difference))
            rows.append(row)
    summary = pd.DataFrame(rows)
    summary.to_csv(out_dir / "replay_summary.csv", index=False)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare xG, npxG and npxG plus a shrunk team penalty rate in the calibration protocol.")
    parser.add_argument("command", choices=["build", "evaluate", "replay", "all"])
    parser.add_argument("--leagues", nargs="+", default=list(CALIBRATION_LEAGUES))
    parser.add_argument("--seasons", nargs="+", type=int, default=list(range(2015, 2026)))
    parser.add_argument("--replay-seasons", nargs="+", type=int, default=list(range(2016, 2026)))
    parser.add_argument("--cutoffs", nargs="+", type=int, default=[5, 10, 20, 30])
    parser.add_argument("--n-sim", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--out-dir", type=Path, default=Path("out/npxg-penalty-rate"))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    features = args.out_dir / "features"
    features.mkdir(parents=True, exist_ok=True)
    if args.command in ("build", "all"):
        join_checks(args.leagues, args.seasons).to_csv(args.out_dir / "join_checks.csv", index=False)
        with ProcessPoolExecutor(args.workers) as pool:
            for job in [pool.submit(build_part, league, season, features) for league in args.leagues for season in args.seasons]:
                job.result()
    data = pd.concat([pd.read_parquet(features / f"{league}_{season}.parquet") for league in args.leagues for season in args.seasons],
                     ignore_index=True)
    if args.command in ("evaluate", "all"):
        report = evaluate(data, args.out_dir)
        print(json.dumps(report["selection"], indent=2, default=float))
    if args.command in ("replay", "all"):
        selection = json.loads((args.out_dir / "selection.json").read_text())
        fits = {name: selection["selection"][name] for name in ("xg", "npxg", "pen")}
        summary = replay(args.out_dir, fits, args.leagues, args.replay_seasons, args.cutoffs, args.n_sim, args.seed, args.workers,
                         selection["held_out_seasons"])
        print(summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
