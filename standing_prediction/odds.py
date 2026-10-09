from __future__ import annotations

import os
import io

import numpy as np
import pandas as pd
import requests

from standing_prediction.utils import normalize_team


THE_ODDS_API_BASE = "https://api.the-odds-api.com/v4"
FOOTBALL_DATA_UK_BASE = "https://www.football-data.co.uk/mmz4281"


def implied_probs_from_decimal_odds(
    home_odds, draw_odds, away_odds, *, eps=1e-12
):
    odds = np.array([home_odds, draw_odds, away_odds], dtype=float)
    odds = np.clip(odds, eps, None)
    p_raw = 1.0 / odds
    p = p_raw / p_raw.sum()
    return float(p[0]), float(p[1]), float(p[2])


def fetch_the_odds_api_h2h_probs(
    *,
    sport_key,
    api_key=None,
    regions="uk",
    odds_format="decimal",
    date_format="iso",
    days=180,
    timeout=30,
):
    api_key = api_key or os.getenv("ODDS_API_KEY") or os.getenv("ODDS_DATA_API_KEY")
    if not api_key:
        raise ValueError("Missing ODDS_API_KEY / ODDS_DATA_API_KEY for The Odds API.")

    url = f"{THE_ODDS_API_BASE}/sports/{sport_key}/odds"
    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": "h2h",
        "oddsFormat": odds_format,
        "dateFormat": date_format,
        "days": int(days),
    }

    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    rows = []
    for match in data:
        match_id = match.get("id")
        home = match.get("home_team")
        away = match.get("away_team")
        commence_time = match.get("commence_time")
        if not home or not away:
            continue

        for bookmaker in match.get("bookmakers", []) or []:
            for market in bookmaker.get("markets", []) or []:
                if market.get("key") != "h2h":
                    continue
                outcomes = market.get("outcomes", []) or []
                prices = {}
                for o in outcomes:
                    name = o.get("name")
                    price = o.get("price")
                    if not name or price is None:
                        continue
                    try:
                        prices[str(name)] = float(price)
                    except (TypeError, ValueError):
                        continue

                if home not in prices or away not in prices:
                    continue
                draw_price = prices.get("Draw")
                if draw_price is None:
                    # Some books/sports may omit draws; skip.
                    continue

                p_home, p_draw, p_away = implied_probs_from_decimal_odds(
                    prices[home], draw_price, prices[away]
                )
                rows.append(
                    {
                        "match_id": match_id,
                        "commence_time": commence_time,
                        "home_team": home,
                        "away_team": away,
                        "p_home_book": p_home,
                        "p_draw_book": p_draw,
                        "p_away_book": p_away,
                    }
                )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["commence_time"] = pd.to_datetime(df["commence_time"], errors="coerce", utc=True)
    df["home_norm"] = df["home_team"].astype(str).apply(normalize_team)
    df["away_norm"] = df["away_team"].astype(str).apply(normalize_team)

    # Average implied probabilities across bookmakers for the same match pairing.
    grouped = (
        df.groupby(["home_norm", "away_norm"], as_index=False)
        .agg(
            {
                "home_team": "first",
                "away_team": "first",
                "commence_time": "min",
                "p_home_book": "mean",
                "p_draw_book": "mean",
                "p_away_book": "mean",
            }
        )
        .reset_index(drop=True)
    )
    # Renormalize after averaging.
    total = grouped["p_home_book"] + grouped["p_draw_book"] + grouped["p_away_book"]
    grouped["p_home_book"] = grouped["p_home_book"] / total
    grouped["p_draw_book"] = grouped["p_draw_book"] / total
    grouped["p_away_book"] = grouped["p_away_book"] / total
    return grouped


def fetch_football_data_uk_probs(
    *,
    league_code,
    season_start_year,
    bookmaker_prefix="B365",
    timeout=30,
):
    season_code = _football_data_uk_season_code(season_start_year)
    url = f"{FOOTBALL_DATA_UK_BASE}/{season_code}/{league_code}.csv"

    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()

    # Files are UTF-8 with BOM.
    content = resp.content.decode("utf-8-sig", errors="replace")
    df = pd.read_csv(io.StringIO(content))

    cols = {
        "home": f"{bookmaker_prefix}H",
        "draw": f"{bookmaker_prefix}D",
        "away": f"{bookmaker_prefix}A",
    }
    for k, col in cols.items():
        if col not in df.columns:
            raise ValueError(f"football-data.co.uk CSV missing column {col} for {k} odds.")

    out = df[["Date", "Time", "HomeTeam", "AwayTeam", cols["home"], cols["draw"], cols["away"]]].copy()
    out = out.rename(
        columns={
            "Date": "date",
            "Time": "time",
            "HomeTeam": "home_team",
            "AwayTeam": "away_team",
            cols["home"]: "home_odds",
            cols["draw"]: "draw_odds",
            cols["away"]: "away_odds",
        }
    )
    out["date"] = pd.to_datetime(out["date"], dayfirst=True, errors="coerce", utc=True)
    # time is sometimes empty; keep date-only in that case.
    out["time"] = out["time"].astype(str).str.strip()
    has_time = out["time"].str.match(r"^\\d{1,2}:\\d{2}$", na=False)
    if has_time.any():
        out.loc[has_time, "date"] = pd.to_datetime(
            out.loc[has_time, "date"].dt.strftime("%Y-%m-%d") + " " + out.loc[has_time, "time"],
            errors="coerce",
            utc=True,
        )
    out["home_norm"] = out["home_team"].astype(str).apply(normalize_team)
    out["away_norm"] = out["away_team"].astype(str).apply(normalize_team)

    out = out.dropna(subset=["home_odds", "draw_odds", "away_odds"])
    probs = np.array(
        [
            1.0 / out["home_odds"].to_numpy(dtype=float),
            1.0 / out["draw_odds"].to_numpy(dtype=float),
            1.0 / out["away_odds"].to_numpy(dtype=float),
        ]
    ).T
    probs = probs / probs.sum(axis=1, keepdims=True)
    out["p_home_book"] = probs[:, 0]
    out["p_draw_book"] = probs[:, 1]
    out["p_away_book"] = probs[:, 2]
    return out[["date", "home_team", "away_team", "home_norm", "away_norm", "p_home_book", "p_draw_book", "p_away_book"]]


def fetch_football_data_uk_matches(
    *,
    league_code,
    season_start_year,
    timeout=30,
):
    """
    Fetch match results from football-data.co.uk and return a frame compatible with
    our modelling code: utcDate, matchday, homeTeam, awayTeam, homeGoals, awayGoals.
    """
    season_code = _football_data_uk_season_code(season_start_year)
    url = f"{FOOTBALL_DATA_UK_BASE}/{season_code}/{league_code}.csv"

    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()

    content = resp.content.decode("utf-8-sig", errors="replace")
    df = pd.read_csv(io.StringIO(content))
    required = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"football-data.co.uk CSV missing required columns: {sorted(missing)}")

    out = df[["Date", "Time", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]].copy()
    out = out.rename(
        columns={
            "Date": "date",
            "Time": "time",
            "HomeTeam": "homeTeam",
            "AwayTeam": "awayTeam",
            "FTHG": "homeGoals",
            "FTAG": "awayGoals",
        }
    )
    out["utcDate"] = pd.to_datetime(out["date"], dayfirst=True, errors="coerce", utc=True)
    out["time"] = out["time"].astype(str).str.strip()
    has_time = out["time"].str.match(r"^\\d{1,2}:\\d{2}$", na=False)
    if has_time.any():
        out.loc[has_time, "utcDate"] = pd.to_datetime(
            out.loc[has_time, "utcDate"].dt.strftime("%Y-%m-%d") + " " + out.loc[has_time, "time"],
            errors="coerce",
            utc=True,
        )

    out["homeGoals"] = pd.to_numeric(out["homeGoals"], errors="coerce")
    out["awayGoals"] = pd.to_numeric(out["awayGoals"], errors="coerce")
    out = out.dropna(subset=["homeGoals", "awayGoals", "utcDate"]).copy()

    out = out.sort_values("utcDate").reset_index(drop=True)

    teams = pd.unique(out[["homeTeam", "awayTeam"]].values.ravel("K"))
    matches_per_round = max(1, len(teams) // 2)
    out["matchday"] = (np.arange(len(out)) // matches_per_round) + 1

    return out[["utcDate", "matchday", "homeTeam", "awayTeam", "homeGoals", "awayGoals"]]


def _football_data_uk_season_code(season_start_year):
    start = season_start_year % 100
    end = (season_start_year + 1) % 100
    return f"{start:02d}{end:02d}"


COMPETITION_TO_FOOTBALL_DATA_UK_LEAGUE = {
    # football-data.org -> football-data.co.uk codes
    "PD": "SP1",  # Spain La Liga
    "PL": "E0",  # England Premier League
    "BL1": "D1",  # Germany Bundesliga
    "SA": "I1",  # Italy Serie A
    "FL1": "F1",  # France Ligue 1
}
