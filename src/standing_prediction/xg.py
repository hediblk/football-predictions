from __future__ import annotations

import json

import numpy as np
import pandas as pd
import requests

from standing_prediction.utils import cache_max_age, cached_get, normalize_team

UNDERSTAT_BASE = "https://understat.com"
XG_PROVIDER = "understat"
XG_COLUMNS = ["home_xg", "away_xg"]
# Understat covers these leagues from 2014/15 with post-match, penalty-inclusive shot xG.
COMPETITION_TO_UNDERSTAT_LEAGUE = {
    "PD": "La_liga", "PL": "EPL", "BL1": "Bundesliga", "SA": "Serie_A", "FL1": "Ligue_1",
}
UNDERSTAT_FIRST_SEASON = 2014


def fetch_understat_matches(*, competition, season, timeout=30, cache_dir=".cache/understat", use_cache=True):
    """Completed league matches with Understat xG; kickoff times are UTC."""
    league = COMPETITION_TO_UNDERSTAT_LEAGUE.get(competition)
    if league is None:
        raise ValueError(f"Understat does not cover competition {competition}.")
    if season < UNDERSTAT_FIRST_SEASON:
        raise ValueError(f"Understat xG starts in {UNDERSTAT_FIRST_SEASON}/{UNDERSTAT_FIRST_SEASON + 1 - 2000}.")
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"})
    content = cached_get(f"{UNDERSTAT_BASE}/getLeagueData/{league}/{season}", session=session, timeout=timeout,
                         cache_dir=cache_dir if use_cache else None, max_age=cache_max_age(season))
    rows = []
    for match in json.loads(content).get("dates", []):
        if not match.get("isResult"):
            continue
        rows.append({
            "understat_id": match["id"], "utcDate": match["datetime"],
            "homeTeam": match["h"]["title"], "awayTeam": match["a"]["title"],
            "homeGoals": match["goals"]["h"], "awayGoals": match["goals"]["a"],
            "home_xg": match["xG"]["h"], "away_xg": match["xG"]["a"],
        })
    columns = ["understat_id", "utcDate", "homeTeam", "awayTeam", "homeGoals", "awayGoals", *XG_COLUMNS]
    out = pd.DataFrame(rows, columns=columns)
    out["utcDate"] = pd.to_datetime(out["utcDate"], utc=True, errors="coerce")
    for column in ["homeGoals", "awayGoals", *XG_COLUMNS]:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    return out.sort_values("utcDate").reset_index(drop=True)


def attach_xg(matches, xg, *, max_kickoff_gap=pd.Timedelta(days=2)):
    """Join one season's xG onto its results by team pair, checking kickoff and final score.

    Rows that cannot be matched unambiguously keep missing xG; nothing is imputed.
    """
    out = matches.copy()
    for column in XG_COLUMNS:
        out[column] = np.nan
    coverage = {"provider": XG_PROVIDER, "finished": 0, "matched": 0, "unmatched": 0,
                "kickoff_mismatch": 0, "score_mismatch": 0}
    finished = out["homeGoals"].notna() & out["awayGoals"].notna()
    coverage["finished"] = int(finished.sum())
    if xg is None or xg.empty or not finished.any():
        coverage["unmatched"] = coverage["finished"]
        out.attrs["xg_coverage"] = coverage
        return out
    source = xg.assign(home_norm=xg["homeTeam"].map(normalize_team), away_norm=xg["awayTeam"].map(normalize_team))
    # Each home/away pairing occurs once per league season; duplicates make the join ambiguous.
    source = source.drop_duplicates(["home_norm", "away_norm"], keep=False).set_index(["home_norm", "away_norm"])
    kickoffs = pd.to_datetime(out["utcDate"], utc=True, errors="coerce")
    for index in out.index[finished]:
        key = (normalize_team(out.at[index, "homeTeam"]), normalize_team(out.at[index, "awayTeam"]))
        if key not in source.index:
            coverage["unmatched"] += 1
            continue
        row = source.loc[key]
        if pd.isna(kickoffs[index]) or abs(row["utcDate"] - kickoffs[index]) > max_kickoff_gap:
            coverage["kickoff_mismatch"] += 1
            continue
        if (row["homeGoals"], row["awayGoals"]) != (out.at[index, "homeGoals"], out.at[index, "awayGoals"]):
            coverage["score_mismatch"] += 1
            continue
        out.loc[index, XG_COLUMNS] = row[XG_COLUMNS].to_numpy(dtype=float)
        coverage["matched"] += 1
    out.attrs["xg_coverage"] = coverage
    return out


def load_season_xg(matches, *, competition, season, cache=True):
    """Attach Understat xG to one season's results; unavailable seasons keep missing xG."""
    try:
        xg = fetch_understat_matches(competition=competition, season=season, use_cache=cache)
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        out = attach_xg(matches, None)
        out.attrs["xg_coverage"]["error"] = type(exc).__name__
        return out
    return attach_xg(matches, xg)
