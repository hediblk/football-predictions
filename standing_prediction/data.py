from __future__ import annotations

import json
import os
import warnings

import numpy as np
import pandas as pd
import requests

from standing_prediction.utils import cache_max_age, cached_get

BASE_URL = "https://api.football-data.org/v4"
MATCH_COLUMNS = ["id", "utcDate", "matchday", "status", "homeTeam", "awayTeam", "homeTeamId", "awayTeamId", "homeGoals", "awayGoals"]
STANDING_COLUMNS = ["position", "team", "played", "points", "goals_for", "goals_against", "goal_diff"]


class FootballDataClient:
    def __init__(self, cache_dir=".cache/football-data", use_cache=True):
        self.api_key = os.getenv("FOOTBALL_DATA_API_KEY")
        if not self.api_key:
            raise ValueError("FOOTBALL_DATA_API_KEY is not set.")
        self.session = requests.Session()
        self.session.headers.update({"X-Auth-Token": self.api_key})
        self.cache_dir = cache_dir if use_cache else None

    def get(self, path, params=None):
        content = cached_get(
            f"{BASE_URL}{path}", params=params, session=self.session,
            cache_dir=self.cache_dir, max_age=cache_max_age((params or {}).get("season")),
        )
        return json.loads(content)


def fetch_standings(client, competition="PD", season=None):
    params = {"season": season} if season is not None else None
    data = client.get(f"/competitions/{competition}/standings", params=params)
    tables = data["standings"]
    table = next((s["table"] for s in tables if s.get("type") == "TOTAL"), tables[0]["table"])
    rows = []
    for row in table:
        rows.append({
            "position": row["position"], "team": row["team"]["name"],
            "played": row["playedGames"], "points": row["points"],
            "goals_for": row["goalsFor"], "goals_against": row["goalsAgainst"],
            "goal_diff": row["goalDifference"],
        })
    return pd.DataFrame(rows, columns=STANDING_COLUMNS)


def fetch_matches(client, competition="PD", season=None, status="FINISHED"):
    params = {}
    if status is not None:
        params["status"] = status
    if season is not None:
        params["season"] = season
    data = client.get(f"/competitions/{competition}/matches", params=params)
    return _matches_to_df(data["matches"])


def _matches_to_df(matches):
    rows = []
    for match in matches:
        full_time = match.get("score", {}).get("fullTime", {})
        rows.append({
            "id": match.get("id"), "utcDate": match.get("utcDate"),
            "matchday": match.get("matchday"), "status": match.get("status"),
            "homeTeam": match["homeTeam"]["name"], "awayTeam": match["awayTeam"]["name"],
            "homeTeamId": match["homeTeam"].get("id"), "awayTeamId": match["awayTeam"].get("id"),
            "homeGoals": full_time.get("home"), "awayGoals": full_time.get("away"),
        })
    df = pd.DataFrame(rows, columns=MATCH_COLUMNS)
    df["utcDate"] = pd.to_datetime(df["utcDate"], errors="coerce", utc=True)
    return df


def validate_schedule(matches, standings):
    required = {"homeTeam", "awayTeam", "status", "homeGoals", "awayGoals"}
    if not required.issubset(matches.columns):
        raise ValueError(f"Schedule is missing columns: {sorted(required - set(matches.columns))}")
    if standings.empty or standings["team"].duplicated().any():
        raise ValueError("Standings must contain each team exactly once.")
    teams = set(standings["team"])
    participants = set(matches["homeTeam"]) | set(matches["awayTeam"])
    unknown = participants - teams
    if unknown:
        raise ValueError(f"Schedule contains teams absent from standings: {sorted(unknown)}")
    if matches[["homeTeam", "awayTeam"]].duplicated().any():
        raise ValueError("Schedule contains duplicate home/away pairings.")
    expected = {(home, away) for home in teams for away in teams if home != away}
    actual = set(zip(matches["homeTeam"], matches["awayTeam"]))
    if actual != expected:
        raise ValueError(f"Incomplete double round-robin schedule: {len(expected - actual)} missing fixtures, {len(actual - expected)} invalid fixtures.")
    if matches["status"].isna().any():
        raise ValueError("Schedule contains fixtures without a status.")
    finished = matches[matches["status"].eq("FINISHED")]
    scores = finished[["homeGoals", "awayGoals"]].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(scores).all() or (scores < 0).any() or (scores != np.floor(scores)).any():
        raise ValueError("Finished fixtures must have nonnegative integer scores.")
    played = pd.concat([finished["homeTeam"], finished["awayTeam"]]).value_counts()
    reported = standings.set_index("team")["played"].astype(int)
    if not played.reindex(reported.index, fill_value=0).eq(reported).all():
        raise ValueError("Finished fixture counts disagree with standings; refresh the data before forecasting.")
    remaining = matches[~matches["status"].eq("FINISHED")].copy()
    live = remaining["status"].isin(["IN_PLAY", "PAUSED", "LIVE", "EXTRA_TIME", "PENALTY_SHOOTOUT"])
    if live.any():
        warnings.warn(f"{int(live.sum())} fixtures are in progress; they will be simulated from kickoff.", stacklevel=2)
    return remaining


def standings_from_matches(matches, teams=None, competition="PD"):
    if teams is None:
        teams = pd.unique(matches[["homeTeam", "awayTeam"]].to_numpy().ravel())
    elif isinstance(teams, pd.DataFrame):
        teams = teams["team"]
    table = pd.DataFrame(0, index=pd.Index(list(teams), name="team"), columns=["played", "points", "goals_for", "goals_against"])
    finished = matches[matches["status"].eq("FINISHED")] if "status" in matches else matches
    for row in finished.itertuples(index=False):
        home, away = row.homeTeam, row.awayTeam
        hg, ag = int(row.homeGoals), int(row.awayGoals)
        if home not in table.index or away not in table.index:
            raise ValueError("Match contains a team absent from the requested standings.")
        table.loc[[home, away], "played"] += 1
        table.loc[home, ["goals_for", "goals_against"]] += [hg, ag]
        table.loc[away, ["goals_for", "goals_against"]] += [ag, hg]
        table.loc[home, "points"] += 3 if hg > ag else int(hg == ag)
        table.loc[away, "points"] += 3 if ag > hg else int(hg == ag)
    table["goal_diff"] = table["goals_for"] - table["goals_against"]
    table = table.reset_index().sort_values(["points", "goal_diff", "goals_for", "team"], ascending=[False, False, False, True]).reset_index(drop=True)
    table["position"] = np.arange(1, len(table) + 1)
    return table[STANDING_COLUMNS]
