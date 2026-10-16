# Offline xG plus-minus experiment (squads plan Task 7): do actual lineups improve later-season
# team-game xG? Team terms are the existing quasi-Poisson xG strengths (`fit_xg_strengths`, stored
# decay and ridge, current plus two prior seasons), refitted at 00:00 UTC on each match day from
# earlier kickoffs only. Player effects are additive xG per 90 on top of that prediction,
# ridge-shrunk toward a pluggable prior. Nothing here feeds forecasts or the site.
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.sparse.linalg import lsqr

from standing_prediction.defaults import DEFAULT_FIT
from standing_prediction.xg import fit_xg_strengths

DATA = Path("data/players/understat")
LAMBDAS = (10.0, 30.0, 100.0, 300.0, 1000.0, 3000.0, 10000.0, 30000.0)
EPOCH = pd.Timestamp(0, tz="UTC")
WARMUP_SEASON = 2014  # team strengths only; player rows start the season after


# Shrink every effect to zero. A replacement (Task 6's EA prior) gets the same arguments and returns
# (attack, defence) prior means in xG per 90, using only information before `before_season`.
def flat_prior(players, before_season):
    return np.zeros(len(players)), np.zeros(len(players))


def load_data(root=DATA):
    games = pd.read_csv(root / "team_games.csv.gz")
    games["date"] = pd.to_datetime(games["date"], utc=True)
    files = sorted(path for path in root.glob("*/*.csv.gz"))
    apps = pd.concat([pd.read_csv(path).assign(league=path.parent.name, season=int(path.name[:4]))
                      for path in files], ignore_index=True)
    keys = set(zip(games["match_id"], games["side"]))
    if set(zip(apps["match_id"], apps["side"])) != keys:
        raise ValueError("Appearance and team-game files cover different team-games.")
    return games, apps


def team_only_predictions(games, *, xi, lambda_reg, prior_seasons=DEFAULT_FIT["prior_seasons"]):
    home = games[games["side"] == "h"].rename(columns={
        "team": "homeTeam", "opponent": "awayTeam", "date": "utcDate", "xg_for": "home_xg", "xg_against": "away_xg"})
    rows = []
    for (league, season), block in home.groupby(["league", "season"]):
        history = home[(home["league"] == league) & home["season"].between(season - prior_seasons, season)]
        for day, fixtures in block.groupby(block["utcDate"].dt.normalize()):
            fit = fit_xg_strengths(history, reference_date=day, xi=xi, lambda_reg=lambda_reg)
            for fixture in fixtures.itertuples():
                if fit is None:
                    rows.append((fixture.match_id, np.nan, np.nan))
                    continue
                att, dfn = fit.attack, fit.defense
                h, a = fixture.homeTeam, fixture.awayTeam
                rows.append((fixture.match_id,
                             np.exp(fit.intercept + fit.home_advantage + att.get(h, 0.0) + dfn.get(a, 0.0)),
                             np.exp(fit.intercept + att.get(a, 0.0) + dfn.get(h, 0.0))))
    pred = pd.DataFrame(rows, columns=["match_id", "h", "a"]).melt("match_id", var_name="side", value_name="team_pred")
    return games.merge(pred, on=["match_id", "side"], validate="one_to_one")


# Each team-game's lineup values, minutes / 90. "absolute" is the specified sum. "centred" subtracts
# the team's usual lineup: the same decay and seasons as the team fit, over the team's earlier
# kickoffs in that league, so team strengths that already contain the regulars do not count them twice.
def lineup_entries(games, apps, *, lineup, xi, prior_seasons=DEFAULT_FIT["prior_seasons"]):
    if lineup == "absolute":
        return apps.assign(value=apps["minutes"] / 90)[["match_id", "side", "player_id", "value"]]
    parts = []
    for (league, team), block in games.groupby(["league", "team"]):
        block = block.sort_values("date")
        kickoff = (block["date"] - EPOCH).dt.total_seconds().to_numpy() / 86400
        day = (block["date"].dt.normalize() - EPOCH).dt.total_seconds().to_numpy() / 86400
        age = day[:, None] - kickoff[None, :]
        season = block["season"].to_numpy()
        weight = np.where((age > 0) & (season[None, :] >= season[:, None] - prior_seasons), np.exp(-xi * age), 0.0)
        mine = apps[(apps["league"] == league) & (apps["team"] == team)]
        minutes = mine.pivot_table(index="match_id", columns="player_id", values="minutes", aggfunc="sum",
                                   fill_value=0).reindex(block["match_id"], fill_value=0)
        total = weight.sum(axis=1, keepdims=True)
        usual = np.divide(weight @ minutes.to_numpy(float), total, out=np.zeros(minutes.shape), where=total > 0)
        value = (minutes.to_numpy(float) - usual) / 90
        r, c = np.nonzero(np.abs(value) >= 0.005)
        parts.append(pd.DataFrame({"match_id": block["match_id"].to_numpy()[r], "side": block["side"].to_numpy()[r],
                                   "player_id": minutes.columns.to_numpy()[c], "value": value[r, c]}))
    return pd.concat(parts, ignore_index=True)


# One row per team-game (attacking side): its lineup in the attack columns and the opponent's in
# the defence columns.
def design(games, entries, players):
    row = pd.Series(np.arange(len(games)), index=pd.MultiIndex.from_frame(games[["match_id", "side"]]))
    col = pd.Series(np.arange(len(players)), index=players)
    own = row.reindex(pd.MultiIndex.from_frame(entries[["match_id", "side"]])).to_numpy()
    opp = row.reindex(pd.MultiIndex.from_arrays([entries["match_id"], entries["side"].map({"h": "a", "a": "h"})])).to_numpy()
    pcol = col.reindex(entries["player_id"]).to_numpy()
    keep = ~np.isnan(own) & ~np.isnan(pcol)
    value = entries["value"].to_numpy(float)[keep]
    own, opp, pcol = own[keep].astype(int), opp[keep].astype(int), pcol[keep].astype(int)
    return sparse.csr_matrix((np.r_[value, value], (np.r_[own, opp], np.r_[2 * pcol, 2 * pcol + 1])),
                             shape=(len(games), 2 * len(players)))


def fit_effects(X, residual, lam, prior_mean):
    target = residual - X @ prior_mean
    return prior_mean + lsqr(X, target, damp=np.sqrt(lam), atol=1e-10, btol=1e-10, iter_lim=20000)[0]


def interleave(attack, defence):
    out = np.empty(2 * len(attack))
    out[0::2], out[1::2] = attack, defence
    return out


class Fold:
    def __init__(self, games, apps, entries, train_seasons, eval_seasons, prior):
        self.train = games[games["season"].isin(train_seasons)].reset_index(drop=True)
        self.eval = games[games["season"].isin(eval_seasons)].reset_index(drop=True)
        train_apps = apps[apps["season"].isin(train_seasons)]
        self.players = pd.Index(np.sort(train_apps["player_id"].unique()))
        self.minutes = train_apps.groupby("player_id")["minutes"].sum().reindex(self.players).to_numpy()
        self.X = design(self.train, entries, self.players)
        self.X_eval = design(self.eval, entries, self.players)
        self.residual = (self.train["xg_for"] - self.train["team_pred"]).to_numpy()
        self.prior_mean = interleave(*prior(self.players, min(eval_seasons)))

    def predict(self, lam):
        beta = fit_effects(self.X, self.residual, lam, self.prior_mean)
        return self.eval["team_pred"].to_numpy() + self.X_eval @ beta, beta


def metrics(frame, pred_col):
    error = frame[pred_col] - frame["xg_for"]
    return {"rows": len(frame), "mae": error.abs().mean(), "rmse": np.sqrt((error ** 2).mean()), "bias": error.mean()}


# Team-only against player model, with a match-clustered standard error on the MSE gain.
def compare(frame):
    out = {}
    for name, column in (("team", "team_pred"), ("player", "player_pred")):
        out.update({f"{name}_{key}": value for key, value in metrics(frame, column).items() if key != "rows"})
    gain = (frame["team_pred"] - frame["xg_for"]) ** 2 - (frame["player_pred"] - frame["xg_for"]) ** 2
    per_match = gain.groupby(frame["match_id"]).sum()
    out["rows"] = len(frame)
    out["mse_gain"] = gain.mean()
    out["mse_gain_se"] = per_match.std(ddof=1) * np.sqrt(len(per_match)) / len(frame)
    return out


def run(out_dir, *, lineup="centred", root=DATA, prior=flat_prior, lambdas=LAMBDAS, reuse=True):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    xi, lambda_reg = DEFAULT_FIT["xi"], DEFAULT_FIT["lambda_reg"]
    games, apps = load_data(root)
    cached = out_dir / "team_only.csv.gz"
    if reuse and cached.exists():
        games = pd.read_csv(cached, parse_dates=["date"])
    else:
        games = team_only_predictions(games, xi=xi, lambda_reg=lambda_reg)
        games.to_csv(cached, index=False)
    if lineup == "starters":
        # Pre-kickoff information only: a start counts as a full game, a substitute appearance as none.
        apps = apps.assign(minutes=np.where(apps["appearance"] == "starter", 90, 0))
    entries = lineup_entries(games, apps, lineup="absolute" if lineup == "absolute" else "centred", xi=xi)
    out_dir = out_dir / lineup
    out_dir.mkdir(exist_ok=True)
    games = games[games["season"] > WARMUP_SEASON].reset_index(drop=True)
    apps = apps[apps["season"] > WARMUP_SEASON]
    seasons = sorted(games["season"].unique())

    # One-season-ahead folds for every ridge strength; season t is fitted on seasons before t.
    fold_rows, preds, folds = [], {}, {}
    for season in seasons[1:]:
        fold = Fold(games, apps, entries, seasons[:seasons.index(season)], [season], prior)
        folds[season] = fold
        for lam in lambdas:
            pred, _ = fold.predict(lam)
            frame = fold.eval.assign(player_pred=pred)
            preds[season, lam] = frame
            fold_rows.append({"season": season, "lambda": lam, **compare(frame)})
    folds_table = pd.DataFrame(fold_rows)

    # Ridge strength for season s: lowest pooled MSE over the earlier one-season-ahead folds.
    chosen, frames = {}, []
    for season in seasons[2:]:
        earlier = folds_table[folds_table["season"] < season]
        pooled = earlier.assign(mse=earlier["player_rmse"] ** 2 * earlier["rows"]).groupby("lambda")["mse"].sum()
        chosen[season] = float(pooled.idxmin())
        frames.append(preds[season, chosen[season]].assign(lam=chosen[season]))
    evaluated = pd.concat(frames, ignore_index=True)
    known = []
    for season in seasons[2:]:
        fold = folds[season]
        played = apps[apps["season"] == season]
        known.append({"season": season, "known_minutes_share":
                      played["player_id"].isin(fold.players).mul(played["minutes"]).sum() / played["minutes"].sum()})
    coverage = pd.DataFrame(known)

    by_league_season = pd.DataFrame([{"league": league, "season": season, "lambda": chosen[season], **compare(frame)}
                                     for (league, season), frame in evaluated.groupby(["league", "season"])])
    by_season = pd.DataFrame([{"season": season, "lambda": chosen[season], **compare(frame)}
                              for season, frame in evaluated.groupby("season")]).merge(coverage, on="season")
    by_league = pd.DataFrame([{"league": league, **compare(frame)} for league, frame in evaluated.groupby("league")])
    overall = compare(evaluated)

    # Learning curve: the latest three seasons fitted on only their k most recent prior seasons.
    curve = []
    for season in seasons[-3:]:
        prior_seasons = seasons[:seasons.index(season)]
        for k in range(1, len(prior_seasons) + 1):
            fold = Fold(games, apps, entries, prior_seasons[-k:], [season], prior)
            pred, _ = fold.predict(chosen[season])
            curve.append({"season": season, "train_seasons": k, "lambda": chosen[season],
                          **compare(fold.eval.assign(player_pred=pred))})
    curve = pd.DataFrame(curve)

    effects, final_lambda, sigma = final_effects(games, apps, entries, seasons, folds_table, prior)
    wowy = with_or_without(games, apps, effects.head(20)["player_id"])

    folds_table.to_csv(out_dir / "folds.csv", index=False)
    by_league_season.to_csv(out_dir / "by_league_season.csv", index=False)
    by_season.to_csv(out_dir / "by_season.csv", index=False)
    by_league.to_csv(out_dir / "by_league.csv", index=False)
    curve.to_csv(out_dir / "learning_curve.csv", index=False)
    effects.to_csv(out_dir / "player_effects.csv", index=False)
    wowy.to_csv(out_dir / "with_or_without.csv", index=False)
    summary = {"team_model": {"function": "standing_prediction.xg.fit_xg_strengths", "xi": xi,
                              "lambda_reg": lambda_reg, "prior_seasons": DEFAULT_FIT["prior_seasons"],
                              "reference": "00:00 UTC on match day, earlier kickoffs only"},
               "lineup": lineup, "prior": prior.__name__, "lambdas": list(lambdas),
               "chosen_lambda": {int(k): v for k, v in chosen.items()},
               "final_lambda": final_lambda, "final_sigma": sigma, "overall": overall,
               "team_games": len(games), "evaluated_team_games": len(evaluated)}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=float) + "\n")
    return summary


# v' (X'X + lam I)^-1 v for each column of `vectors`, by Jacobi-preconditioned block CG.
def posterior_variances(X, lam, vectors, iters=500, tol=1e-8):
    diag = np.asarray(X.multiply(X).sum(axis=0)).ravel() + lam
    B = vectors.toarray() if sparse.issparse(vectors) else vectors
    x = np.zeros_like(B)
    r = B.copy()
    z = r / diag[:, None]
    p = z.copy()
    rz = (r * z).sum(axis=0)
    for _ in range(iters):
        Ap = X.T @ (X @ p) + lam * p
        alpha = rz / (p * Ap).sum(axis=0)
        x += alpha * p
        r -= alpha * Ap
        if np.sqrt((r * r).sum(axis=0)).max() < tol:
            break
        z = r / diag[:, None]
        rz_new = (r * z).sum(axis=0)
        p = z + (rz_new / rz) * p
        rz = rz_new
    return (B * x).sum(axis=0)


# All seasons, with the ridge strength the pooled one-season-ahead folds prefer.
def final_effects(games, apps, entries, seasons, folds_table, prior, min_minutes=900, chunk=400):
    pooled = folds_table.assign(mse=folds_table["player_rmse"] ** 2 * folds_table["rows"]).groupby("lambda")["mse"].sum()
    lam = float(pooled.idxmin())
    fold = Fold(games, apps, entries, seasons, [seasons[-1]], prior)
    beta = fit_effects(fold.X, fold.residual, lam, fold.prior_mean)
    fitted = fold.X @ beta
    sigma = float(np.sqrt(np.mean((fold.residual - fitted) ** 2)))
    played = apps[apps["season"].isin(seasons)]
    latest = played.sort_values("date").groupby("player_id").tail(1).set_index("player_id")
    starts = played[played["position"] != "Sub"]
    position = starts.groupby("player_id")["position"].agg(lambda s: s.mode().iloc[0])
    effects = pd.DataFrame({
        "player_id": fold.players, "minutes": fold.minutes,
        "attack": beta[0::2], "defence": beta[1::2]})
    effects["net"] = effects["attack"] - effects["defence"]
    effects = effects.join(latest[["name", "team", "league", "season"]], on="player_id")
    effects["position"] = effects["player_id"].map(position).fillna("Sub")
    eligible = np.flatnonzero(fold.minutes >= min_minutes)
    n = 2 * len(fold.players)
    var_net = np.full(len(fold.players), np.nan)
    for start in range(0, len(eligible), chunk):
        idx = eligible[start:start + chunk]
        cols = np.arange(len(idx))
        vectors = sparse.csc_matrix((np.r_[np.ones(len(idx)), -np.ones(len(idx))],
                                     (np.r_[2 * idx, 2 * idx + 1], np.r_[cols, cols])), shape=(n, len(idx)))
        var_net[idx] = posterior_variances(fold.X, lam, vectors)
    effects["net_sd"] = sigma * np.sqrt(var_net)
    effects = effects.sort_values("net", ascending=False, key=abs).reset_index(drop=True)
    return effects, lam, sigma


# Sanity check only: team-only residual net xG in a player's club-seasons with him on for `min_on`+
# minutes against games he did not appear in. Opponents and team-mates are not adjusted.
def with_or_without(games, apps, player_ids, min_on=45):
    rows = []
    games = games.assign(net_residual=(games["xg_for"] - games["team_pred"])
                         - (games["xg_against"] - games.merge(
                             games[["match_id", "side", "team_pred"]].assign(side=lambda d: d["side"].map({"h": "a", "a": "h"})),
                             on=["match_id", "side"], suffixes=("", "_opp"))["team_pred_opp"].to_numpy()))
    for pid in player_ids:
        mine = apps[apps["player_id"] == pid]
        spells = mine[["league", "season", "team"]].drop_duplicates()
        pool = games.merge(spells, on=["league", "season", "team"])
        minutes = mine.set_index(["match_id", "side"])["minutes"]
        on = pool.set_index(["match_id", "side"]).index.map(minutes).to_numpy(dtype=float)
        with_ = pool["net_residual"][on >= min_on]
        without = pool["net_residual"][np.isnan(on)]
        rows.append({"player_id": pid, "with_games": len(with_), "without_games": len(without),
                     "with_mean": with_.mean(), "without_mean": without.mean() if len(without) else np.nan,
                     "difference": with_.mean() - without.mean() if len(without) else np.nan})
    return pd.DataFrame(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline xG plus-minus experiment (Task 7).")
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--out-dir", type=Path, default=Path("out/player-impact"))
    parser.add_argument("--lineup", nargs="+", choices=["centred", "starters", "absolute"],
                        default=["centred", "starters", "absolute"])
    parser.add_argument("--refit-team", action="store_true", help="Recompute the cached team-only predictions.")
    args = parser.parse_args(argv)
    for lineup in args.lineup:
        summary = run(args.out_dir, lineup=lineup, root=args.data, reuse=not args.refit_team)
        print(json.dumps(summary, indent=2, default=float))


if __name__ == "__main__":
    main()
