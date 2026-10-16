# EA-rating prior for the player impact model (squads plan Task 7b). Prior mean = slope × (EA overall −
# position-group mean), with separate attack and defence slopes. The rating comes from the latest
# vintage available before the evaluation season's first kickoff, joined through Task 6's link table.
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse.linalg import lsqr

PLAYERS = Path("data/players")
CACHE = Path(".cache/players")
LOOKBACK = pd.Timedelta(days=365)
GROUPS = {"GK": "GK", "CB": "DEF", "LB": "DEF", "RB": "DEF", "LWB": "DEF", "RWB": "DEF",
          "CDM": "MID", "CM": "MID", "CAM": "MID", "LM": "MID", "RM": "MID",
          "ST": "ATT", "CF": "ATT", "LW": "ATT", "RW": "ATT"}


def season_cutoff(season, root=PLAYERS):
    games = pd.read_csv(root / "understat/team_games.csv.gz", usecols=["season", "date"])
    dates = pd.to_datetime(games.loc[games["season"] == season, "date"], utc=True)
    return dates.min() if len(dates) else pd.Timestamp(f"{season}-08-01", tz="UTC")


# One row per linked Understat player: EA overall and position group from the latest vintage before
# the cutoff that lists him, looking back at most a year. Only `matched` links are used.
def ea_ratings(before_season, *, root=PLAYERS, cache=CACHE):
    links = pd.read_csv(root / "understat_ea_links.csv", usecols=["understat_id", "status", "ea_id"])
    links = links[links["status"] == "matched"].drop_duplicates("understat_id").astype({"ea_id": int})
    cutoff = season_cutoff(before_season, root)
    vintages = json.loads((root / "ea/vintages.json").read_text())["vintages"]
    eligible = sorted((v for v in vintages if cutoff - LOOKBACK <= pd.Timestamp(v["available_from"]) < cutoff),
                      key=lambda v: v["available_from"], reverse=True)
    need, found = set(links["ea_id"]), []
    for vintage in eligible:
        rows = pd.read_csv(cache / vintage["file"], usecols=["ea_id", "overall", "positions"])
        rows = rows[rows["ea_id"].isin(need) & rows["overall"].notna()].assign(vintage=vintage["id"])
        found.append(rows)
        need -= set(rows["ea_id"])
        if not need:
            break
    if not found:
        return pd.DataFrame(columns=["overall", "group", "vintage"], index=pd.Index([], name="understat_id"))
    ratings = pd.concat(found).assign(group=lambda d: d["positions"].str.split(",").str[0].str.strip().map(GROUPS))
    return links.merge(ratings, on="ea_id").set_index("understat_id")[["overall", "group", "vintage"]]


# Ridge with unpenalised slopes on the prior's two directions G, by Frisch–Waugh: the slopes are
# regressed on what the ridge cannot already explain. Regressing shrunk effects on ratings would
# attenuate them instead.
def profiled_slopes(X, residual, lam, G):
    def annihilate(v):
        return v - X @ lsqr(X, v, damp=np.sqrt(lam), atol=1e-10, btol=1e-10, iter_lim=20000)[0]

    MG = np.column_stack([annihilate(G[:, 0]), annihilate(G[:, 1])])
    return np.linalg.solve(G.T @ MG, MG.T @ residual)


class EaPrior:
    name = "ea_prior"

    def __init__(self, root=PLAYERS, cache=CACHE):
        self.root, self.cache = root, cache
        self.ratings, self.slopes = {}, {}

    def rated(self, players, before_season):
        if before_season not in self.ratings:
            self.ratings[before_season] = ea_ratings(before_season, root=self.root, cache=self.cache)
        return self.ratings[before_season].reindex(players)

    # EA overall minus the mean of rated `players` in the same position group; 0 when unrated.
    def score(self, players, before_season):
        rated = self.rated(players, before_season)
        centred = rated["overall"] - rated.groupby("group")["overall"].transform("mean")
        return centred.fillna(0.0).to_numpy()

    # Each training row uses the ratings available before its own season, as evaluation does. Ratings
    # dated at the evaluation season already reflect the training seasons' results (hindsight).
    # Returns the rows' prior directions G (attack, defence); the prior offset is G @ slopes.
    def fit(self, X, residual, lam, players, row_seasons, before_season):
        G = np.zeros((X.shape[0], 2))
        for season in np.unique(row_seasons):
            rows = np.flatnonzero(row_seasons == season)
            score = self.score(players, season)
            G[rows] = np.column_stack([X[rows][:, 0::2] @ score, X[rows][:, 1::2] @ score])
        self.slopes[before_season] = tuple(profiled_slopes(X, residual, lam, G))
        return G

    def __call__(self, players, before_season):
        attack, defence = self.slopes.get(before_season, (0.0, 0.0))
        score = self.score(players, before_season)
        return attack * score, defence * score
