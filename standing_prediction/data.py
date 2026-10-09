from __future__ import annotations

import os

import pandas as pd
import requests

BASE_URL = "https://api.football-data.org/v4"


class FootballDataClient:
    def __init__(self):
        self.api_key = os.getenv("FOOTBALL_DATA_API_KEY")
        if not self.api_key:
            raise ValueError("FOOTBALL_DATA_API_KEY is not set.")
        self.session = requests.Session()
        self.session.headers.update({"X-Auth-Token": self.api_key})

    def get(self, path, params=None):
        response = self.session.get(f"{BASE_URL}{path}", params=params, timeout=30)
        response.raise_for_status()
        return response.json()


def fetch_standings(client, competition="PD", season=None):
    params = {"season": season} if season else None
    data = client.get(f"/competitions/{competition}/standings", params=params)
    table = data["standings"][0]["table"]
    rows = []
    for row in table:
        rows.append(
            {
                "position": row["position"],
                "team": row["team"]["name"],
                "played": row["playedGames"],
                "points": row["points"],
                "goals_for": row["goalsFor"],
                "goals_against": row["goalsAgainst"],
                "goal_diff": row["goalDifference"],
            }
        )
    return pd.DataFrame(rows)


def fetch_matches(
    client,
    competition="PD",
    season=None,
    status="FINISHED",
):
    params = {"status": status}
    if season:
        params["season"] = season
    data = client.get(f"/competitions/{competition}/matches", params=params)
    return _matches_to_df(data["matches"])


def _matches_to_df(matches):
    rows = []
    for match in matches:
        score = match.get("score", {})
        full_time = score.get("fullTime", {})
        rows.append(
            {
                "utcDate": match.get("utcDate"),
                "matchday": match.get("matchday"),
                "status": match.get("status"),
                "homeTeam": match["homeTeam"]["name"],
                "awayTeam": match["awayTeam"]["name"],
                "homeGoals": full_time.get("home"),
                "awayGoals": full_time.get("away"),
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df["utcDate"] = pd.to_datetime(df["utcDate"])
    return df
