from __future__ import annotations

import io
import json
import os

import numpy as np
import pandas as pd

from standing_prediction.utils import cache_max_age, cached_get, normalize_team

THE_ODDS_API_BASE = "https://api.the-odds-api.com/v4"
FOOTBALL_DATA_UK_BASE = "https://www.football-data.co.uk/mmz4281"
PROB_COLUMNS = ["p_home_book", "p_draw_book", "p_away_book"]


def implied_probs_from_decimal_odds(home_odds, draw_odds, away_odds, *, eps=1e-12):
    odds = np.array([home_odds, draw_odds, away_odds], dtype=float)
    if not np.isfinite(odds).all() or (odds <= 1).any():
        raise ValueError("Decimal odds must be finite and greater than 1.")
    probs = 1.0 / odds
    probs /= probs.sum()
    return tuple(float(p) for p in probs)


def fetch_the_odds_api_h2h_probs(
    *, sport_key, api_key=None, regions="uk", odds_format="decimal",
    date_format="iso", days=180, timeout=30,
):
    api_key = api_key or os.getenv("ODDS_API_KEY") or os.getenv("ODDS_DATA_API_KEY")
    if not api_key:
        raise ValueError("Missing ODDS_API_KEY / ODDS_DATA_API_KEY for The Odds API.")
    if odds_format != "decimal" or date_format != "iso":
        raise ValueError("Only decimal odds and ISO timestamps are supported.")
    if int(days) <= 0:
        raise ValueError("Odds horizon must be a positive number of days.")
    params = {
        "apiKey": api_key, "regions": regions, "markets": "h2h",
        "oddsFormat": odds_format, "dateFormat": date_format,
        "commenceTimeTo": (pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=int(days))).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    data = json.loads(cached_get(f"{THE_ODDS_API_BASE}/sports/{sport_key}/odds", params=params, timeout=timeout))
    columns = ["match_id", "commence_time", "observed_at", "home_team", "away_team", "home_norm", "away_norm", *PROB_COLUMNS]
    df = pd.DataFrame(_h2h_quotes(data))
    if df.empty:
        return pd.DataFrame(columns=columns)
    for column in ("commence_time", "observed_at"):
        df[column] = pd.to_datetime(df[column], errors="coerce", utc=True)
    df["home_norm"] = df["home_team"].apply(normalize_team)
    df["away_norm"] = df["away_team"].apply(normalize_team)
    # A consensus is only known after its newest component quote was observed.
    grouped = df.groupby(["home_norm", "away_norm", "commence_time"], as_index=False).agg({
        "match_id": "first", "home_team": "first", "away_team": "first",
        "observed_at": lambda values: values.max() if values.notna().all() else pd.NaT,
        **{column: "mean" for column in PROB_COLUMNS},
    })
    grouped[PROB_COLUMNS] = grouped[PROB_COLUMNS].div(grouped[PROB_COLUMNS].sum(axis=1), axis=0)
    return grouped[columns]


ARCHIVE_COLUMNS = ["fetched_at", "competition", "match_id", "commence_time", "observed_at", "home_team", "away_team",
                   "books", "last_update", *PROB_COLUMNS, "pinnacle_home", "pinnacle_draw", "pinnacle_away"]

PRICE_COLUMNS = [
    "fetched_at", "competition", "match_id", "commence_time", "observed_at", "home_team", "away_team",
    "average_home", "average_draw", "average_away", "best_home", "best_draw", "best_away",
    "pinnacle_home", "pinnacle_draw", "pinnacle_away", "average_over_2_5", "average_under_2_5",
    "best_over_2_5", "best_under_2_5", "pinnacle_over_2_5", "pinnacle_under_2_5",
]


def _api_decimal(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) and value > 1 else None


def the_odds_api_archive_snapshots(
    *, sport_key, competition, api_key=None, regions="eu", timeout=30, fetched_at=None, markets="h2h",
    on_response_headers=None,
):
    api_key = api_key or os.getenv("ODDS_API_KEY") or os.getenv("ODDS_DATA_API_KEY")
    if not api_key:
        raise ValueError("Missing ODDS_API_KEY / ODDS_DATA_API_KEY for The Odds API.")
    fetched_at = pd.Timestamp.now(tz="UTC") if fetched_at is None else pd.to_datetime(fetched_at, utc=True)
    params = {"apiKey": api_key, "regions": regions, "markets": markets,
              "oddsFormat": "decimal", "dateFormat": "iso"}
    request = {"params": params, "timeout": timeout}
    if on_response_headers is not None:
        request["on_response_headers"] = on_response_headers
    events = json.loads(cached_get(f"{THE_ODDS_API_BASE}/sports/{sport_key}/odds", **request))
    quotes = pd.DataFrame(_h2h_quotes(events))
    if quotes.empty:
        archive = pd.DataFrame(columns=ARCHIVE_COLUMNS)
    else:
        keys = ["match_id", "commence_time", "home_team", "away_team"]
        out = quotes.groupby(keys, as_index=False).agg(
            books=("bookmaker", "nunique"), last_update=("observed_at", "max"),
            **{column: (column, "mean") for column in PROB_COLUMNS})
        out[PROB_COLUMNS] = out[PROB_COLUMNS].div(out[PROB_COLUMNS].sum(axis=1), axis=0)
        pinnacle = quotes[quotes["bookmaker"].eq("pinnacle")].drop_duplicates("match_id").set_index("match_id")[PROB_COLUMNS]
        pinnacle.columns = ["pinnacle_home", "pinnacle_draw", "pinnacle_away"]
        out = out.join(pinnacle, on="match_id")
        out["fetched_at"] = out["observed_at"] = fetched_at.isoformat()
        out["competition"] = competition
        archive = out[ARCHIVE_COLUMNS].sort_values(["commence_time", "home_team"]).reset_index(drop=True)
    prices = _raw_price_snapshot(events, competition, fetched_at)
    return archive, prices


def the_odds_api_snapshot(*, sport_key, competition, api_key=None, regions="eu", timeout=30, fetched_at=None):
    """Current 1X2 prices for one competition, one row per fixture, for the dated odds archive.

    Rows hold the bookmaker count, the mean of de-margined bookmaker probabilities and Pinnacle's
    de-margined probabilities when it quotes. `observed_at` is the fetch time, so the archive can be
    passed as an odds snapshot for forecasts made after it. Costs one API credit per region.
    """
    return the_odds_api_archive_snapshots(
        sport_key=sport_key, competition=competition, api_key=api_key, regions=regions,
        timeout=timeout, fetched_at=fetched_at,
    )[0]


def _raw_price_snapshot(events, competition, fetched_at):
    rows = []
    for event in events:
        row = {"fetched_at": fetched_at.isoformat(), "observed_at": fetched_at.isoformat(),
               "competition": competition, "match_id": event.get("id"),
               "commence_time": event.get("commence_time"), "home_team": event.get("home_team"),
               "away_team": event.get("away_team")}
        if not row["home_team"] or not row["away_team"]:
            continue
        h2h = {key: [] for key in ("home", "draw", "away")}
        totals = {"over": [], "under": []}
        pinnacle_h2h = {key: None for key in h2h}
        pinnacle_totals = {key: None for key in totals}
        for bookmaker in event.get("bookmakers", []) or []:
            for market in bookmaker.get("markets", []) or []:
                if market.get("key") == "h2h":
                    outcomes = {item.get("name"): _api_decimal(item.get("price"))
                                for item in market.get("outcomes", []) or []}
                    values = {"home": outcomes.get(row["home_team"]), "draw": outcomes.get("Draw"),
                              "away": outcomes.get(row["away_team"])}
                    if all(value is not None for value in values.values()):
                        for side, value in values.items():
                            h2h[side].append(value)
                            if bookmaker.get("key") == "pinnacle":
                                pinnacle_h2h[side] = value
                elif market.get("key") == "totals":
                    outcomes = {item.get("name"): _api_decimal(item.get("price"))
                                for item in market.get("outcomes", []) or []
                                if pd.to_numeric(item.get("point"), errors="coerce") == 2.5}
                    values = {side: outcomes.get(label) for side, label in (("over", "Over"), ("under", "Under"))}
                    if all(value is not None for value in values.values()):
                        for side, value in values.items():
                            totals[side].append(value)
                            if bookmaker.get("key") == "pinnacle":
                                pinnacle_totals[side] = value
        for side, values in h2h.items():
            row[f"average_{side}"] = float(np.mean(values)) if values else np.nan
            row[f"best_{side}"] = max(values) if values else np.nan
            row[f"pinnacle_{side}"] = pinnacle_h2h[side] if pinnacle_h2h[side] is not None else np.nan
        for side, values in totals.items():
            row[f"average_{side}_2_5"] = float(np.mean(values)) if values else np.nan
            row[f"best_{side}_2_5"] = max(values) if values else np.nan
            row[f"pinnacle_{side}_2_5"] = pinnacle_totals[side] if pinnacle_totals[side] is not None else np.nan
        rows.append(row)
    if not rows:
        return pd.DataFrame(columns=PRICE_COLUMNS)
    return pd.DataFrame(rows, columns=PRICE_COLUMNS).sort_values(["commence_time", "home_team"]).reset_index(drop=True)


def _h2h_quotes(events):
    """One row per bookmaker 1X2 quote in a The Odds API response, with de-margined probabilities."""
    rows = []
    for match in events:
        home, away = match.get("home_team"), match.get("away_team")
        if not home or not away:
            continue
        for bookmaker in match.get("bookmakers", []) or []:
            for market in bookmaker.get("markets", []) or []:
                if market.get("key") != "h2h":
                    continue
                prices = {o.get("name"): o.get("price") for o in market.get("outcomes", []) or []}
                if any(prices.get(name) is None for name in (home, "Draw", away)):
                    continue
                try:
                    probs = implied_probs_from_decimal_odds(prices[home], prices["Draw"], prices[away])
                except (ValueError, TypeError):
                    continue
                rows.append({
                    "match_id": match.get("id"), "commence_time": match.get("commence_time"),
                    "observed_at": market.get("last_update") or bookmaker.get("last_update"),
                    "bookmaker": bookmaker.get("key"), "home_team": home, "away_team": away,
                    **dict(zip(PROB_COLUMNS, probs)),
                })
    return rows


def _football_data_csv(league_code, season_start_year, timeout, cache_dir, use_cache):
    season_code = _football_data_uk_season_code(season_start_year)
    url = f"{FOOTBALL_DATA_UK_BASE}/{season_code}/{league_code}.csv"
    content = cached_get(url, timeout=timeout, cache_dir=cache_dir if use_cache else None, max_age=cache_max_age(season_start_year))
    return pd.read_csv(io.StringIO(content))


def _uk_dates(df):
    dates = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce", format="mixed")
    times = df["Time"].astype(str).str.strip() if "Time" in df else pd.Series("", index=df.index)
    has_time = times.str.fullmatch(r"\d{1,2}:\d{2}", na=False)
    if has_time.any():
        dates.loc[has_time] = pd.to_datetime(
            dates.loc[has_time].dt.strftime("%Y-%m-%d") + " " + times.loc[has_time], errors="coerce",
        )
    return dates.dt.tz_localize("Europe/London", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")


def fetch_football_data_uk_probs(
    *, league_code, season_start_year, bookmaker_prefix="B365", timeout=30,
    cache_dir=".cache/football-data-uk", use_cache=True,
):
    df = _football_data_csv(league_code, season_start_year, timeout, cache_dir, use_cache)
    odds_columns = [f"{bookmaker_prefix}{outcome}" for outcome in ("H", "D", "A")]
    required = {"Date", "HomeTeam", "AwayTeam", *odds_columns}
    if not required.issubset(df.columns):
        raise ValueError(f"football-data.co.uk CSV missing columns: {sorted(required - set(df.columns))}")
    decimal = df[odds_columns].apply(pd.to_numeric, errors="coerce")
    valid = np.isfinite(decimal).all(axis=1) & decimal.gt(1).all(axis=1)
    out = df.loc[valid, ["HomeTeam", "AwayTeam"]].rename(columns={"HomeTeam": "home_team", "AwayTeam": "away_team"}).copy()
    out["date"] = _uk_dates(df).loc[valid]
    out["observed_at"] = pd.NaT  # Historical CSVs do not timestamp when odds were available.
    out["home_norm"] = out["home_team"].apply(normalize_team)
    out["away_norm"] = out["away_team"].apply(normalize_team)
    probs = 1.0 / decimal.loc[valid].to_numpy(dtype=float)
    probs /= probs.sum(axis=1, keepdims=True)
    out[PROB_COLUMNS] = probs
    return out[["date", "observed_at", "home_team", "away_team", "home_norm", "away_norm", *PROB_COLUMNS]]


def fetch_football_data_uk_matches(
    *, league_code, season_start_year, timeout=30,
    cache_dir=".cache/football-data-uk", use_cache=True,
):
    df = _football_data_csv(league_code, season_start_year, timeout, cache_dir, use_cache)
    return _football_data_matches(df)


def _football_data_matches(df):
    required = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
    if not required.issubset(df.columns):
        raise ValueError(f"football-data.co.uk CSV missing columns: {sorted(required - set(df.columns))}")
    out = df[["HomeTeam", "AwayTeam", "FTHG", "FTAG"]].rename(columns={
        "HomeTeam": "homeTeam", "AwayTeam": "awayTeam", "FTHG": "homeGoals", "FTAG": "awayGoals",
    }).copy()
    out["utcDate"] = _uk_dates(df)
    for column in ("homeGoals", "awayGoals"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out = out.dropna(subset=["homeGoals", "awayGoals", "utcDate"]).sort_values("utcDate").reset_index(drop=True)
    out["status"] = "FINISHED"
    teams = pd.unique(out[["homeTeam", "awayTeam"]].to_numpy().ravel())
    out["matchday"] = np.arange(len(out)) // max(1, len(teams) // 2) + 1
    return out[["utcDate", "matchday", "status", "homeTeam", "awayTeam", "homeGoals", "awayGoals"]]


def match_odds(fixtures, odds, as_of=None):
    if odds is None or odds.empty or fixtures.empty:
        return {}
    candidates = odds.copy()
    date_column = "commence_time" if "commence_time" in candidates else "date"
    if date_column not in candidates:
        return {}
    candidates["kickoff"] = pd.to_datetime(candidates[date_column], errors="coerce", utc=True)
    if "observed_at" in candidates:
        candidates["observed_at"] = pd.to_datetime(candidates["observed_at"], errors="coerce", utc=True)
    if as_of is not None:
        if "observed_at" not in candidates:
            return {}
        cutoff = pd.to_datetime(as_of, utc=True)
        candidates = candidates[
            candidates["observed_at"].notna() & candidates["observed_at"].le(cutoff)
            & candidates["observed_at"].lt(candidates["kickoff"])
        ].copy()
    if candidates.empty:
        return {}
    for side in ("home", "away"):
        if f"{side}_norm" not in candidates:
            candidates[f"{side}_norm"] = candidates[f"{side}_team"].apply(normalize_team)
    candidates["match_date"] = candidates["kickoff"].dt.tz_convert("Europe/London").dt.date
    probabilities = candidates[PROB_COLUMNS].apply(pd.to_numeric, errors="coerce")
    valid = np.isfinite(probabilities).all(axis=1) & probabilities.ge(0).all(axis=1) & probabilities.sum(axis=1).gt(0)
    candidates = candidates.loc[valid].copy()
    candidates[PROB_COLUMNS] = probabilities.loc[valid].div(probabilities.loc[valid].sum(axis=1), axis=0)
    if "observed_at" in candidates:
        candidates = candidates.sort_values("observed_at")
    lookup = candidates.drop_duplicates(["home_norm", "away_norm", "match_date"], keep="last").set_index(["home_norm", "away_norm", "match_date"])
    matched = {}
    for row in fixtures.itertuples(index=False):
        kickoff = pd.to_datetime(row.utcDate, errors="coerce", utc=True)
        if pd.isna(kickoff):
            continue
        key = (normalize_team(row.homeTeam), normalize_team(row.awayTeam), kickoff.tz_convert("Europe/London").date())
        if key in lookup.index:
            matched[(row.homeTeam, row.awayTeam)] = tuple(float(p) for p in lookup.loc[key, PROB_COLUMNS])
    return matched


def _football_data_uk_season_code(season_start_year):
    start = season_start_year % 100
    end = (season_start_year + 1) % 100
    return f"{start:02d}{end:02d}"


COMPETITION_TO_FOOTBALL_DATA_UK_LEAGUE = {
    "PD": "SP1", "PL": "E0", "BL1": "D1", "SA": "I1", "FL1": "F1",
}
