from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from forecast_calibration.dataset import CALIBRATION_LEAGUES, XG_COMPETITIONS, load_season
from standing_prediction import player_impact
from standing_prediction.data import standings_from_matches
from standing_prediction.defaults import (
    CALIBRATION_VERSION, DEFAULT_FIT, DEFAULT_WEIGHTS, DEFAULT_XG_SCALE, DEFAULT_XG_WEIGHT,
)
from standing_prediction.dixon_coles import outcome_probs_from_matrix, score_matrix_from_rates
from standing_prediction.ensemble import blend_probabilities
from standing_prediction.predict_positions import build_fixture_specs, fit_prediction_models
from standing_prediction.simulate import FixtureSimulationSpec, rank_table, simulate_season_scores
from standing_prediction.utils import normalize_team

METHODS = ("latest", "recent", "missed", "oracle")
WEIGHTS = (0.0, 0.25, 0.5, 1.0, 2.0, 4.0)
HOLDOUT = 2024
HALF_LIFE = 3.0
MISS_DECAY = 0.5
PLAYER_LEAGUES = {"E0": "EPL", "SP1": "La_liga", "D1": "Bundesliga", "I1": "Serie_A", "F1": "Ligue_1"}


def read_history(cache_dir):
    used = {}

    def cached(url, **kwargs):
        key = hashlib.sha256(json.dumps([url, {}], sort_keys=True).encode()).hexdigest()
        folder = "understat" if "understat.com" in url else "football-data-uk"
        path = cache_dir / folder / f"{key}.json"
        raw = path.read_bytes()
        used[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)["content"]

    # Reuse the calibration loader and its joins, but require saved inputs even on a cache miss.
    with patch("standing_prediction.odds.cached_get", cached), patch("standing_prediction.xg.cached_get", cached):
        history = pd.concat([load_season(league, season) for league in CALIBRATION_LEAGUES
                             for season in range(2014, 2026)], ignore_index=True)
    history["match_id"] = pd.to_numeric(history["understat_id"], errors="coerce").astype("Int64")
    if not (history["forecast_at"] < history["utcDate"]).all():
        raise ValueError("A calibration origin is not before kickoff.")
    return history, used


def player_folds(games, apps, out, prior):
    team = player_impact.team_only_predictions(games, xi=DEFAULT_FIT["xi"], lambda_reg=DEFAULT_FIT["lambda_reg"])
    team.to_csv(out / "player_team_only.csv.gz", index=False)
    starts = apps.assign(minutes=np.where(apps["appearance"].eq("starter"), 90, 0))
    entries = player_impact.lineup_entries(team, starts, lineup="centred", xi=DEFAULT_FIT["xi"])
    team = team[team["season"] >= 2015].reset_index(drop=True)
    starts = starts[starts["season"] >= 2015]
    rows, effects, choices = [], {}, []
    for season in range(2015, 2026):
        if season == 2015:
            effects[season] = pd.DataFrame(columns=["attack", "defence"], index=pd.Index([], name="player_id"))
            continue
        fold = player_impact.Fold(team, starts, entries, list(range(2015, season)), [season], prior)
        # Neither held-out season can change the ridge selection. Coefficients still expand annually.
        earlier = pd.DataFrame(rows)
        if season >= 2017:
            earlier = earlier[earlier["season"] < min(season, HOLDOUT)]
            lam = float(earlier.groupby("lambda")["sse"].sum().idxmin())
        else:
            lam = 300.0  # warm-up only, not a tuned forecast result
        _, beta = fold.predict(lam)
        effects[season] = pd.DataFrame({"attack": beta[0::2], "defence": beta[1::2]}, index=fold.players)
        effects[season].rename_axis("player_id").to_csv(out / f"effects_{season}.csv")
        choices.append({"season": season, "lambda": lam, "training_last_season": season - 1})
        if season < HOLDOUT:
            for candidate in player_impact.LAMBDAS:
                prediction, _ = fold.predict(candidate)
                rows.append({"season": season, "lambda": candidate,
                             "sse": float(((prediction - fold.eval["xg_for"]) ** 2).sum()), "rows": len(prediction)})
        print(f"Player effects {season}: ridge {lam:g}, {len(fold.players)} players", flush=True)
    pd.DataFrame(rows).to_csv(out / "player_ridge_folds.csv", index=False)
    pd.DataFrame(choices).to_csv(out / "player_ridge_choices.csv", index=False)
    return effects


def lineup_history(games, apps, history):
    # Match the calibration result/xG availability, also guarding provider date discrepancies.
    timing = history.dropna(subset=["match_id"])[["match_id", "available_at"]]
    if timing["match_id"].duplicated().any():
        raise ValueError("Duplicate Understat fixture identities in calibration history.")
    games = games.merge(timing, on="match_id", how="left", validate="many_to_one")
    fallback = games["date"].dt.tz_convert("Europe/London").dt.strftime("%Y-%m-%d")
    fallback = pd.to_datetime(fallback, utc=True) + pd.Timedelta(days=1)
    games["available_at"] = games["available_at"].fillna(fallback)
    games["available_at"] = pd.concat([games["available_at"], games["date"]], axis=1).max(axis=1)
    games["team"] = games["team"].map(normalize_team)
    apps = apps.assign(team=apps["team"].map(normalize_team))
    result = {}
    for (league, team), block in games.groupby(["league", "team"]):
        block = block.sort_values(["date", "match_id"])
        mine = apps[(apps["league"] == league) & (apps["team"] == team)]
        matrix = mine.assign(start=mine["appearance"].eq("starter").astype(float)).pivot_table(
            index="match_id", columns="player_id", values="start", fill_value=0)
        matrix = matrix.reindex(block["match_id"])
        present = mine.assign(present=1.0).pivot_table(
            index="match_id", columns="player_id", values="present", fill_value=0).gt(0)
        if not matrix.sum(axis=1).eq(11).all():
            raise ValueError("Each archived team-game must have eleven starters.")
        result[league, team] = (block.reset_index(drop=True), matrix, present)
    return games, result


def expected_lineups(block, matrix, present, origin, season):
    eligible = ((block["available_at"] <= origin) & (block["date"] < origin)
                & block["season"].between(season - DEFAULT_FIT["prior_seasons"], season))
    past = block[eligible]
    values = matrix.loc[past["match_id"]]
    # Columns are restricted to earlier appearances; future debuts cannot enter a feature universe.
    values = values.loc[:, present.loc[past["match_id"]].any(axis=0)]
    if past.empty:
        return pd.DataFrame(columns=["usual", "latest", "recent", "missed"], dtype=float)
    age = (origin - past["date"]).dt.total_seconds().to_numpy() / 86400
    usual = np.exp(-DEFAULT_FIT["xi"] * age)
    recent = 2 ** (-np.arange(len(past) - 1, -1, -1) / HALF_LIFE)
    v = values.to_numpy()
    missed = np.argmax(v[::-1] > 0, axis=0)
    share = recent @ v / recent.sum()
    return pd.DataFrame({"usual": usual @ v / usual.sum(), "latest": v[-1], "recent": share,
                         "missed": share * MISS_DECAY ** missed}, index=values.columns)


def lineup_delta(expected, effects, method, actual=None):
    if expected.empty:
        return np.zeros(2)
    shares = expected[method] if method != "oracle" else pd.Series(1.0, index=actual)
    diff = shares.subtract(expected["usual"], fill_value=0)
    # Flat-prior unseen players contribute zero. A replacement prior can supply their effects.
    missing = diff.index.difference(effects.index)
    if len(missing):
        attack, defence = effects.attrs["prior"](missing, effects.attrs["season"])
        effects = pd.concat([effects, pd.DataFrame({"attack": attack, "defence": defence}, index=missing)])
    return diff.to_numpy() @ effects.reindex(diff.index).to_numpy(float)


def fit_at(history, league, season, origin, teams):
    train = history[(history["league"] == league) & history["season"].between(season - DEFAULT_FIT["prior_seasons"], season)
                    & (history["available_at"] <= origin) & (history["utcDate"] < origin)]
    return fit_prediction_models(train, teams=teams, reference_date=origin, **{
        k: DEFAULT_FIT[k] for k in ("xi", "lambda_reg")}, xg_weight=DEFAULT_XG_WEIGHT, xg_scale=DEFAULT_XG_SCALE)


def build_features(history, games, apps, lineups, effects, out, ledger):
    features, xi_scores = [], []
    actual = {key: set(frame["player_id"]) for key, frame in apps[
        apps["appearance"].eq("starter")].groupby(["match_id", "side"])}
    known_games = set(games["match_id"])
    for (league, season), season_matches in history[history["season"] >= 2015].groupby(["league", "season"]):
        teams = sorted(set(season_matches["homeTeam"]) | set(season_matches["awayTeam"]))
        for origin, matches in season_matches.groupby("forecast_at"):
            dc, elo = fit_at(history, league, season, origin, teams)
            expected = {team: expected_lineups(*lineups[PLAYER_LEAGUES[league], team], origin, season)
                        for team in teams if (PLAYER_LEAGUES[league], team) in lineups}
            for match in matches.itertuples():
                if pd.isna(match.match_id) or match.match_id not in known_games:
                    continue
                row = {k: getattr(match, k) for k in ("league", "season", "match_id", "forecast_at", "utcDate",
                                                      "homeTeam", "awayTeam", "book_h", "book_d", "book_a", "odds_source")}
                row["y"] = 0 if match.homeGoals > match.awayGoals else 1 if match.homeGoals == match.awayGoals else 2
                row["home_rate"], row["away_rate"] = dc.expected_goals(match.homeTeam, match.awayTeam)
                row["rho"] = dc.rho
                row.update(dict(zip([f"elo_{c}" for c in "hda"], elo.predict_probs(match.homeTeam, match.awayTeam))))
                shifts = {}
                for side, team in (("h", match.homeTeam), ("a", match.awayTeam)):
                    exp = expected.get(team, pd.DataFrame())
                    starters = actual[match.match_id, side]
                    for method in METHODS:
                        shifts[side, method] = lineup_delta(exp, effects[season], method, starters)
                    # No-history sides remain in forecasts with zero adjustment, but XI quality is unknown.
                    if exp.empty:
                        row[f"{side}_history"] = False
                        continue
                    row[f"{side}_history"] = True
                    universe = exp.index.union(pd.Index(sorted(starters)))
                    target = universe.isin(starters).astype(float)
                    values = exp.reindex(universe, fill_value=0)
                    ledger.writerows((league, season, match.match_id, origin, side, pid, int(y), *v)
                                     for pid, y, v in zip(universe, target, values.to_numpy()))
                    for method in METHODS[:-1]:
                        p = exp[method].reindex(universe, fill_value=0).to_numpy()
                        # Stable player-ID tie breaking; zero-score unseen players cannot enter the top eleven.
                        top = exp[method].sort_values(ascending=False, kind="stable").head(11).index
                        xi_scores.append({"league": league, "season": season, "match_id": match.match_id,
                                          "forecast_at": origin, "side": side, "method": method,
                                          "players": len(universe), "brier": np.mean((p - target) ** 2),
                                          "correct": len(starters.intersection(top)), "start_mass": p.sum(),
                                          "unseen_starters": len(starters.difference(exp.index))})
                for method in METHODS:
                    row[f"{method}_h"] = shifts["h", method][0] + shifts["a", method][1]
                    row[f"{method}_a"] = shifts["a", method][0] + shifts["h", method][1]
                features.append(row)
        print(f"Forecast features {league}/{season}", flush=True)
    frame = pd.DataFrame(features)
    frame.to_csv(out / "features.csv.gz", index=False)
    quality = pd.DataFrame(xi_scores)
    quality.to_csv(out / "xi_predictions.csv.gz", index=False)
    return frame, quality


def probabilities(row, method, weight, odds=False):
    h = row.home_rate * np.exp(weight * getattr(row, f"{method}_h"))
    a = row.away_rate * np.exp(weight * getattr(row, f"{method}_a"))
    _, matrix = score_matrix_from_rates(h, a, row.rho)
    p = blend_probabilities(outcome_probs_from_matrix(matrix), p_elo=(row.elo_h, row.elo_d, row.elo_a),
                            p_odds=(row.book_h, row.book_d, row.book_a) if odds else None, weights=DEFAULT_WEIGHTS)
    return np.asarray(p), matrix


def losses(p, y):
    target = np.eye(3)[y]
    return np.array([-np.log(max(p[y], 1e-12)), np.sum((p - target) ** 2),
                     np.mean((np.cumsum(p)[:2] - np.cumsum(target)[:2]) ** 2)])


def score_features(features, out):
    rows = []
    for i, row in enumerate(features.itertuples()):
        for odds in (False, True):
            if odds and not np.isfinite([row.book_h, row.book_d, row.book_a]).all():
                continue
            baseline = losses(probabilities(row, "latest", 0, odds)[0], row.y)
            for method in METHODS:
                for weight in WEIGHTS:
                    p, _ = probabilities(row, method, weight, odds)
                    loss = losses(p, row.y)
                    record = {"fixture": i, "league": row.league, "season": row.season, "match_id": row.match_id,
                              "forecast_at": row.forecast_at, "odds": odds, "method": method, "weight": weight}
                    for metric, value, base in zip(("log_loss", "brier", "rps"), loss, baseline):
                        record[metric], record[f"{metric}_gain"] = value, base - value
                    rows.append(record)
    frame = pd.DataFrame(rows)
    frame.to_csv(out / "match_scores.csv.gz", index=False)
    return frame


def cluster_se(values, clusters, weights=None):
    values = np.asarray(values, dtype=float)
    weights = np.ones(len(values)) if weights is None else np.asarray(weights, dtype=float)
    mean = np.average(values, weights=weights)
    sums = pd.Series(weights * (values - mean)).groupby(np.asarray(clusters)).sum()
    g = len(sums)
    return float(np.sqrt(g / (g - 1) * np.sum(sums ** 2)) / weights.sum()) if g > 1 else np.nan


def summaries(frame, groups, metrics):
    rows = []
    for key, block in frame.groupby(groups, dropna=False):
        key = key if isinstance(key, tuple) else (key,)
        row = dict(zip(groups, key))
        row["rows"] = len(block)
        # Same league/origin fixtures can share fit and lineup errors.
        clusters = block["league"].astype(str) + "/" + block["forecast_at"].astype(str)
        for metric in metrics:
            weights = block["players"] if metric == "brier" and "players" in block else np.ones(len(block))
            row[metric] = np.average(block[metric], weights=weights)
            row[f"{metric}_se"] = cluster_se(block[metric], clusters, weights)
        rows.append(row)
    return pd.DataFrame(rows)


def select_and_report(scores, quality, out):
    tuning = scores[(scores["season"].between(2017, HOLDOUT - 1)) & ~scores["odds"]]
    grid = tuning.groupby(["method", "weight", "league", "season"])["log_loss"].mean().groupby(["method", "weight"]).mean()
    grid.rename("log_loss").to_csv(out / "weight_selection.csv")
    choices = {method: float(grid.loc[method].idxmin()) for method in METHODS}
    best_method = min(METHODS[:-1], key=lambda method: grid[method, choices[method]])
    selected = scores[np.array([row.weight == choices[row.method] for row in scores.itertuples()])].copy()
    baseline = scores[(scores["weight"] == 0) & (scores["method"] == "latest")].assign(method="baseline")
    selected = pd.concat([baseline, selected], ignore_index=True)
    selected["period"] = np.select([selected["season"] >= HOLDOUT, selected["season"] >= 2017],
                                   ["heldout", "earlier"], default="warmup")
    metrics = [metric + suffix for metric in ("log_loss", "brier", "rps") for suffix in ("", "_gain")]
    for name, groups in (("overall", ["period", "odds", "method", "weight"]),
                         ("by_season", ["season", "odds", "method", "weight"]),
                         ("by_league", ["period", "league", "odds", "method", "weight"]),
                         ("by_league_season", ["league", "season", "odds", "method", "weight"])):
        summaries(selected, groups, metrics).to_csv(out / f"{name}.csv", index=False)
    for name, groups in (("overall", ["method"]), ("by_season", ["season", "method"]),
                         ("by_league", ["league", "method"]), ("by_league_season", ["league", "season", "method"])):
        summaries(quality, groups, ["brier", "correct", "start_mass", "unseen_starters"]).to_csv(
            out / f"xi_{name}.csv", index=False)
    # Explicit baseline and the full heldout grid are available alongside selected variants.
    summaries(scores[(scores["weight"] == 0) & (scores["method"] == "latest")], ["season", "league", "odds"],
              metrics).to_csv(out / "baseline.csv", index=False)
    summaries(scores[scores["season"] >= HOLDOUT], ["odds", "method", "weight"], metrics).to_csv(
        out / "heldout_grid.csv", index=False)
    return {"weights": choices, "expected_method": best_method}


def standings_replay(history, lineups, effects, selection, out, n_sim, seed):
    rows, events = [], []
    method = selection["expected_method"]
    chosen = selection["weights"][method]
    for (league, season), matches in history[history["season"] >= HOLDOUT].groupby(["league", "season"]):
        comp = XG_COMPETITIONS[league]
        teams = sorted(set(matches["homeTeam"]) | set(matches["awayTeam"]))
        table = standings_from_matches(matches, teams=teams, competition=comp)
        order = rank_table(table, matches, competition=comp)
        for round_ in (5, 15, 25):
            counts = matches.groupby("forecast_at").size().sort_index().cumsum()
            origins = counts[counts >= round_ * len(teams) / 2].index
            if not len(origins):
                continue
            origin = origins[0]
            played = matches[(matches["available_at"] <= origin) & (matches["utcDate"] < origin)]
            future = matches[~matches.index.isin(played.index)].sort_values(["utcDate", "homeTeam", "awayTeam"])
            standings = standings_from_matches(played, teams=teams, competition=comp)
            dc, elo = fit_at(history, league, season, origin, teams)
            usual_specs = build_fixture_specs(future, dc=dc, elo=elo, odds=None, max_goals=10, weights=DEFAULT_WEIGHTS)
            expected = {team: expected_lineups(*lineups[PLAYER_LEAGUES[league], team], origin, season)
                        for team in teams if (PLAYER_LEAGUES[league], team) in lineups}
            # Hold these expectations fixed; only kickoffs in the next seven days receive an offset.
            for weight in sorted(set([0.0, chosen])):
                specs = []
                adjusted = 0
                for match, base in zip(future.itertuples(), usual_specs):
                    if not weight or not origin <= match.utcDate < origin + pd.Timedelta(days=7):
                        specs.append(base)
                        continue
                    dh = lineup_delta(expected.get(match.homeTeam, pd.DataFrame()), effects[season], method)
                    da = lineup_delta(expected.get(match.awayTeam, pd.DataFrame()), effects[season], method)
                    h, a = dc.expected_goals(match.homeTeam, match.awayTeam)
                    _, matrix = score_matrix_from_rates(h * np.exp(weight * (dh[0] + da[1])),
                                                        a * np.exp(weight * (da[0] + dh[1])), dc.rho)
                    p = blend_probabilities(outcome_probs_from_matrix(matrix),
                                            p_elo=elo.predict_probs(match.homeTeam, match.awayTeam), weights=DEFAULT_WEIGHTS)
                    masks = [base.scorelines[:, 0] > base.scorelines[:, 1], base.scorelines[:, 0] == base.scorelines[:, 1],
                             base.scorelines[:, 0] < base.scorelines[:, 1]]
                    conditional = tuple(matrix.ravel() * mask / (matrix.ravel() * mask).sum() for mask in masks)
                    specs.append(FixtureSimulationSpec(base.home, base.away, *p, base.scorelines, conditional))
                    adjusted += 1
                counts = simulate_season_scores(specs, standings, n_sim=n_sim, seed=seed, played_matches=played, competition=comp)
                record = {"league": league, "season": season, "forecast_at": origin, "round": round_,
                          "weight": weight, "method": method, "adjusted_fixtures": adjusted}
                for event, positions, winners in (("title", [1], set(order[:1])), ("top_four", [1, 2, 3, 4], set(order[:4]))):
                    p = counts[positions].sum(axis=1).reindex(teams).to_numpy() / n_sim
                    y = np.array([team in winners for team in teams])
                    # Jeffreys smoothing avoids infinite event loss from a finite Monte Carlo zero.
                    p = (p * n_sim + 0.5) / (n_sim + 1)
                    loss = -(y * np.log(p) + (1 - y) * np.log1p(-p))
                    record[f"{event}_log_loss"] = loss.mean()
                    if event == "title":
                        record["champion_log_loss"] = float(-np.log(p[y][0]))
                    for team, prob, target in zip(teams, p, y):
                        events.append({**record, "event": event, "team": team, "probability": prob, "actual": int(target)})
                rows.append(record)
            print(f"Standings {league}/{season} round {round_}", flush=True)
    pd.DataFrame(rows).to_csv(out / "standings.csv", index=False)
    pd.DataFrame(events).to_csv(out / "standings_events.csv", index=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline expected-XI replay; never writes forecast defaults or site data.")
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--data", type=Path, default=player_impact.DATA)
    parser.add_argument("--out-dir", type=Path, default=Path("out/expected-xi"))
    parser.add_argument("--prior", default="standing_prediction.player_impact:flat_prior", help="module:function(players, before_season)")
    parser.add_argument("--n-sim", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--reuse", action="store_true", help="Reuse outputs only when the input/code manifest matches.")
    args = parser.parse_args(argv)
    if args.n_sim < 1:
        parser.error("--n-sim must be positive")
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    module, function = args.prior.split(":")
    prior = getattr(importlib.import_module(module), function)
    history, sources = read_history(args.cache_dir)
    games, apps = player_impact.load_data(args.data)
    files = [*args.data.glob("*/*.csv.gz"), args.data / "team_games.csv.gz", Path(__file__),
             Path(player_impact.__file__), Path(importlib.import_module(module).__file__),
             Path(importlib.import_module("forecast_calibration.dataset").__file__)]
    # Include all model implementation/settings files so cached rates cannot survive a model change.
    files.extend(Path(player_impact.__file__).parent.glob("*.py"))
    files.append(Path(player_impact.__file__).with_name("calibrated_weights.json"))
    manifest = {"inputs": {**sources, **{str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},
                "prior": args.prior, "weights": WEIGHTS, "half_life_games": HALF_LIFE, "miss_decay": MISS_DECAY,
                "holdout_start": HOLDOUT, "calibration": CALIBRATION_VERSION, "n_sim": args.n_sim, "seed": args.seed}
    manifest = json.loads(json.dumps(manifest))
    old = out / "manifest.json"
    reuse = args.reuse and old.exists() and json.loads(old.read_text()) == manifest
    if args.reuse and not reuse:
        raise ValueError("No matching manifest; run without --reuse to rebuild.")
    # An interrupted rebuild must never certify partially overwritten outputs for reuse.
    old.unlink(missing_ok=True)
    if reuse:
        effects = {season: pd.read_csv(out / f"effects_{season}.csv", index_col="player_id") for season in range(2016, 2026)}
        effects[2015] = pd.DataFrame(columns=["attack", "defence"])
    else:
        effects = player_folds(games, apps, out, prior)
    for season, frame in effects.items():
        frame.attrs.update(prior=prior, season=season)
    games, lineups = lineup_history(games, apps, history)
    if reuse:
        features = pd.read_csv(out / "features.csv.gz")
        quality = pd.read_csv(out / "xi_predictions.csv.gz")
        scores = pd.read_csv(out / "match_scores.csv.gz")
    else:
        with gzip.open(out / "xi_probabilities.csv.gz", "wt") as handle:
            ledger = csv.writer(handle)
            ledger.writerow(["league", "season", "match_id", "forecast_at", "side", "player_id", "actual_start",
                             "usual", "latest", "recent", "missed"])
            features, quality = build_features(history, games, apps, lineups, effects, out, ledger)
        scores = score_features(features, out)
    selection = select_and_report(scores, quality, out)
    standings_replay(history, lineups, effects, selection, out, args.n_sim, args.seed)
    coverage = history[history["season"] >= 2015].groupby(["league", "season"]).size().rename("calibration_fixtures").to_frame()
    coverage["evaluated_fixtures"] = features.groupby(["league", "season"]).size()
    coverage["excluded_fixtures"] = coverage["calibration_fixtures"] - coverage["evaluated_fixtures"]
    coverage.to_csv(out / "coverage.csv")
    summary = {**selection, "fixtures": len(features), "xi_team_games": len(quality) // 3,
               "no_history_team_games": int(2 * len(features) - len(quality) // 3), "holdout_start": HOLDOUT,
               "first_selection_season": 2017, "seed": args.seed, "n_sim": args.n_sim,
               "integration": "None; requires a later explicit calibration task and a positive heldout gain."}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    old.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
