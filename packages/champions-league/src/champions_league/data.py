from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import logging

import pandas as pd
from dotenv import load_dotenv

from standing_prediction.data import FootballDataClient, STANDING_COLUMNS, fetch_standings, standings_from_matches
from standing_prediction.xg import load_season_xg

from champions_league.identities import AREA_LEAGUES, canonical_team
from champions_league.sources import (
    CSV_LEAGUES, EUROPE_COMMIT, EURO_CUPS_COMMIT, azerbaijan_matches, csv_matches, czech_matches,
    european_supplement, slovak_matches, ukrainian_matches,
)

LOG = logging.getLogger(__name__)
DOMESTIC_LEAGUES = [*CSV_LEAGUES, "AUT", "NOR", "CZ1", "SK1", "UA1", "AZ1"]
DOMESTIC_ADAPTERS = {"CZ1": czech_matches, "SK1": slovak_matches, "UA1": ukrainian_matches, "AZ1": azerbaijan_matches}
EUROPEAN_COMPETITIONS = {"CL", "EL", "ECL"}
RELOCATED_VENUES = {
    2023: "Volksparkstadion, Hamburg", 2024: "Veltins-Arena, Gelsenkirchen",
    2025: "Stadion Miejski, Kraków", 2026: "Stamford Bridge, London",
}
VENUE_SOURCES = [
    "https://shakhtar.com/en/news/2024/july/2_news/2_veltinsarena/",
    "https://shakhtar.com/en/news/2025/july/17_news/17_european-matches-to-be-held-in-krakow/",
    "https://shakhtar.com/en/news/2026/august/21_news/21_shakhtar_stamford_bridge/",
    "https://fcdynamo.com/en/news/dinamo-gratime-domasni-matci-ligi-jevropi-v-gamburzi",
    "https://www.uefa.com/uefaeuropaleague/match/2042125--m-tel-aviv-vs-real-sociedad/matchinfo/",
    "https://www.uefa.com/uefaeuropaleague/news/0293-1c413aae026a-d0c1fb03c125-1000/",
]
PERIODS = ["fullTime", "regularTime", "extraTime", "penalties"]


@dataclass
class UCLInputs:
    fixtures: pd.DataFrame
    standings: pd.DataFrame
    history: pd.DataFrame
    team_leagues: dict
    coverage: pd.DataFrame
    metadata: dict


def matches_from_api(matches, *, season):
    rows = []
    for match in matches:
        score = match.get("score", {})
        duration = score.get("duration", "REGULAR")
        regular = score.get("fullTime", {}) if duration == "REGULAR" else score.get("regularTime", {})
        if match.get("status") != "FINISHED":
            regular = {}
        if match.get("status") == "FINISHED" and any(regular.get(side) is None for side in ("home", "away")):
            raise ValueError(f"Finished UCL fixture {match.get('id')} has no reliable 90-minute score.")
        home, away = match["homeTeam"], match["awayTeam"]
        home_name, away_name = canonical_team(home["name"]), canonical_team(away["name"])
        relocated = home_name == "shakhtar donetsk" and season in RELOCATED_VENUES
        rows.append({
            "id": match.get("id"), "utcDate": match.get("utcDate"), "stage": match.get("stage"),
            "matchday": match.get("matchday"), "status": match.get("status"),
            "homeTeam": home_name, "awayTeam": away_name, "homeTeamId": home.get("id"), "awayTeamId": away.get("id"),
            "homeGoals": regular.get("home"), "awayGoals": regular.get("away"),
            "duration": duration, "winner": score.get("winner"),
            **{period: score.get(period, {"home": None, "away": None}) for period in PERIODS},
            "neutral": match.get("stage") == "FINAL" or relocated,
            "venue": RELOCATED_VENUES[season] if relocated else match.get("venue"),
            "relocated": relocated, "season": season, "competition": "CL",
            "source": "https://api.football-data.org/v4/competitions/CL/matches",
        })
    out = pd.DataFrame(rows)
    out["utcDate"] = pd.to_datetime(out["utcDate"], utc=True)
    out["available_at"] = out["utcDate"] + pd.Timedelta(hours=3)
    return out


def fetch_ucl_fixtures(client=None, *, season=2026, cache=True):
    if client is None:
        load_dotenv()
        client = FootballDataClient(use_cache=cache)
    return matches_from_api(client.get("/competitions/CL/matches", params={"season": season})["matches"], season=season)


def _known_fixtures(fixtures, origin, season):
    out = fixtures.copy()
    future = out["available_at"] >= origin
    out.loc[future, ["homeGoals", "awayGoals", "winner"]] = None
    out.loc[future, "status"] = "SCHEDULED"
    out.loc[future, "duration"] = "REGULAR"
    for period in PERIODS:
        out.loc[future, period] = pd.Series([{"home": None, "away": None} for _ in range(int(future.sum()))], index=out.index[future], dtype=object)
    league = out[out["stage"].eq("LEAGUE_STAGE")]
    if not league.empty and not league["status"].eq("FINISHED").all():
        return out[out["stage"].eq("LEAGUE_STAGE")].copy()
    draw_dates = {
        2024: {"PLAYOFFS": "2025-01-31 12:00Z", "LAST_16": "2025-02-21 12:00Z"},
        2025: {"PLAYOFFS": "2026-01-30 12:00Z", "LAST_16": "2026-02-27 12:00Z"},
    }
    previous = "LEAGUE_STAGE"
    for stage in ["PLAYOFFS", "LAST_16", "QUARTER_FINALS", "SEMI_FINALS", "FINAL"]:
        dates = fixtures.loc[fixtures["stage"].eq(previous), "available_at"]
        available = dates.max() if not dates.empty else origin
        draw_date = draw_dates.get(season, {}).get(stage)
        if draw_date:
            available = max(available, pd.Timestamp(draw_date))
        if origin < available:
            out = out[~out["stage"].eq(stage)]
        previous = stage
    return out.reset_index(drop=True)


def _domestic(league, season, cache):
    if league in DOMESTIC_ADAPTERS:
        data = DOMESTIC_ADAPTERS[league](season, cache=cache)
    else:
        data = csv_matches(league, season, cache=cache)
    if league in {"PL", "PD", "BL1", "SA", "FL1"}:
        data = load_season_xg(data, competition=league, season=season, cache=cache)
    return data


def load_inputs(*, season=2026, as_of=None, prior_seasons=2, cache=True, client=None):
    if not 0 <= prior_seasons <= 2:
        raise ValueError("prior_seasons must be between 0 and 2.")
    load_dotenv()
    origin = pd.Timestamp.now(tz="UTC") if as_of is None else pd.to_datetime(as_of, utc=True)
    client = client or FootballDataClient(use_cache=cache)
    raw_fixtures = fetch_ucl_fixtures(client, season=season, cache=cache)
    official = fetch_standings(client, competition="CL", season=season)
    display_names = {canonical_team(name): name for name in official["team"]}
    official["team"] = official["team"].map(canonical_team)
    team_leagues, provider_ids, api_frames, errors = {}, {}, [], []
    for year in range(season - prior_seasons, season + 1):
        try:
            clubs = client.get("/competitions/CL/teams", params={"season": year})["teams"]
            for club in clubs:
                name, area = canonical_team(club["name"]), club.get("area", {}).get("name")
                if area:
                    team_leagues[name] = AREA_LEAGUES.get(area, f"country:{area}")
                provider_ids[str(club["id"])] = name
                display_names.setdefault(name, club.get("shortName") or club["name"])
            api_frames.append(raw_fixtures if year == season else fetch_ucl_fixtures(client, season=year, cache=cache))
        except (KeyError, ValueError, RuntimeError, OSError) as exc:
            if year == season:
                raise
            errors.append({"source": "football-data.org", "season": year, "error": str(exc)})
    source_audits, domestic_frames = [], []
    leagues = sorted(set(DOMESTIC_LEAGUES) | ({"SC0"} if "SC0" in team_leagues.values() else set()))
    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs = {pool.submit(_domestic, league, year, cache): (league, year)
                for league in leagues for year in range(season - prior_seasons, season + 1)}
        for future in as_completed(jobs):
            league, year = jobs[future]
            try:
                data = future.result()
            except (KeyError, ValueError, RuntimeError, OSError) as exc:
                error = {"competition": league, "season": year, "error": str(exc)}
                errors.append(error)
                LOG.warning("Domestic source unavailable: %s %s (%s)", league, year, exc)
                continue
            for column in ["homeTeam", "awayTeam"]:
                for name in data[column].unique():
                    canonical = canonical_team(name)
                    display_names.setdefault(canonical, name)
                    team_leagues[canonical] = league
                data[column] = data[column].map(canonical_team)
            source_audits.append({"competition": league, "season": year, "source": data.attrs.get("source"),
                                  "matches": len(data), "latest_result": data.attrs.get("latest"),
                                  "xg": data.attrs.get("xg_coverage"), "stage_urls": data.attrs.get("stage_urls"),
                                  "reconciliation": data.attrs.get("reconciliation")})
            domestic_frames.append(data)
    for league, code in [("PL", "PL"), ("PD", "PD"), ("BL1", "BL1"), ("SA", "SA"), ("FL1", "FL1"), ("P1", "PPL"), ("N1", "DED")]:
        try:
            payload = client.get(f"/competitions/{code}/matches", params={"season": season})
            api = matches_from_api([match for match in payload["matches"] if match["status"] == "FINISHED"], season=season)
            if api.empty:
                continue
            api["competition"] = api["homeLeague"] = api["awayLeague"] = league
            api["source"] = f"https://api.football-data.org/v4/competitions/{code}/matches"
            for match in payload["matches"]:
                for side in ["homeTeam", "awayTeam"]:
                    name = canonical_team(match[side]["name"])
                    team_leagues[name] = league
                    display_names.setdefault(name, match[side]["name"])
            current = [data for data in domestic_frames if not data.empty and data["competition"].iloc[0] == league and data["season"].iloc[0] == season]
            disagreements = []
            if current:
                csv = current[0]
                overlap = pd.Series(False, index=csv.index)
                for match in api.itertuples(index=False):
                    same = csv["homeTeam"].eq(match.homeTeam) & csv["awayTeam"].eq(match.awayTeam) & (csv["utcDate"] - match.utcDate).abs().le(pd.Timedelta(days=2))
                    if same.any() and not csv.loc[same, ["homeGoals", "awayGoals"]].eq([match.homeGoals, match.awayGoals]).all().all():
                        disagreements.append({"home": match.homeTeam, "away": match.awayTeam, "date": match.utcDate.isoformat()})
                    overlap |= same
                merged = pd.concat([csv.loc[~overlap], api], ignore_index=True)
                domestic_frames = [data for data in domestic_frames if data is not csv]
            else:
                merged = api
            if league in {"PL", "PD", "BL1", "SA", "FL1"}:
                merged = load_season_xg(merged, competition=league, season=season, cache=cache)
            domestic_frames.append(merged)
            source_audits.append({"competition": league, "season": season, "source": api["source"].iloc[0],
                                  "matches": len(api), "latest_result": api["utcDate"].max().isoformat(),
                                  "csv_score_disagreements_overridden": disagreements, "xg": merged.attrs.get("xg_coverage")})
        except (KeyError, ValueError, RuntimeError, OSError) as exc:
            errors.append({"competition": league, "season": season, "source": "football-data.org domestic refresh", "error": str(exc)})
            LOG.warning("Current domestic API refresh unavailable: %s (%s)", league, exc)
    try:
        supplements = european_supplement(cache=cache) if season - prior_seasons <= 2024 <= season else []
    except (KeyError, ValueError, RuntimeError, OSError) as exc:
        supplements = []
        errors.append({"source": "openfootball European supplements", "error": str(exc)})
    for data in supplements:
        for side in ["home", "away"]:
            for name, league in zip(data[f"{side}Team"], data[f"{side}League"]):
                canonical = canonical_team(name)
                display_names.setdefault(canonical, name)
                team_leagues.setdefault(canonical, league)
            data[f"{side}Team"] = data[f"{side}Team"].map(canonical_team)
        relocated = data["homeTeam"].isin(["shakhtar donetsk", "dynamo kyiv", "maccabi tel aviv"])
        relocated |= data["homeTeam"].eq("besiktas") & data["awayTeam"].eq("maccabi tel aviv") & data["utcDate"].eq(pd.Timestamp("2024-11-28", tz="UTC"))
        data.loc[relocated, "neutral"] = True
        source_audits.append({"competition": data["competition"].iloc[0], "season": 2024,
                              "source": data.attrs.get("source"), "matches": len(data), "latest_result": data.attrs.get("latest")})
    for data in api_frames:
        for side in ["home", "away"]:
            data[f"{side}League"] = data[f"{side}Team"].map(team_leagues)
        source_audits.append({"competition": "CL", "season": int(data["season"].iloc[0]),
                              "source": data["source"].iloc[0], "matches": int(data["status"].eq("FINISHED").sum()),
                              "latest_result": data.loc[data["status"].eq("FINISHED"), "utcDate"].max().isoformat()})
    history = pd.concat([*domestic_frames, *api_frames, *supplements], ignore_index=True)
    finished = history["status"].isna() | history["status"].eq("FINISHED")
    history = history[finished & history["available_at"].lt(origin) & history["homeGoals"].notna() & history["awayGoals"].notna()].copy()
    history = history[history["utcDate"].ge(pd.Timestamp(year=season - prior_seasons, month=1 if "NOR" in leagues else 7, day=1, tz="UTC"))]
    xg_unavailable = history["utcDate"].dt.normalize() + pd.Timedelta(days=1) >= origin
    history.loc[xg_unavailable, ["home_xg", "away_xg"]] = float("nan")
    history["homeLeague"] = history["homeTeam"].map(team_leagues)
    history["awayLeague"] = history["awayTeam"].map(team_leagues)
    if history[["homeLeague", "awayLeague"]].isna().any().any():
        missing = sorted(set(history.loc[history["homeLeague"].isna(), "homeTeam"]) | set(history.loc[history["awayLeague"].isna(), "awayTeam"]))
        raise ValueError(f"Unmapped European team leagues: {missing}.")
    duplicate_key = ["competition", "homeTeam", "awayTeam"]
    history["match_date"] = history["utcDate"].dt.date
    duplicate_key.append("match_date")
    conflicts = history.groupby(duplicate_key)[["homeGoals", "awayGoals"]].nunique().gt(1).any(axis=1)
    if conflicts.any():
        raise ValueError("Overlapping result sources disagree on a score.")
    history = history.sort_values(["utcDate", "source"]).drop_duplicates(duplicate_key).drop(columns="match_date").reset_index(drop=True)
    fixtures = _known_fixtures(raw_fixtures, origin, season)
    league = fixtures[fixtures["stage"].eq("LEAGUE_STAGE")]
    if len(league) != 144:
        raise ValueError(f"Expected 144 league-phase fixtures; received {len(league)}.")
    standings = standings_from_matches(league, teams=official["team"])
    visible_finished = league["status"].eq("FINISHED").sum()
    reported_finished = raw_fixtures[raw_fixtures["stage"].eq("LEAGUE_STAGE") & raw_fixtures["status"].eq("FINISHED")].shape[0]
    use_official = visible_finished == reported_finished
    if use_official:
        for column in ["played", "points", "goals_for", "goals_against"]:
            observed = standings.set_index("team")[column].sort_index()
            reported = official.set_index("team")[column].sort_index()
            if not observed.equals(reported):
                raise ValueError(f"Official UCL standings disagree with fixture {column} totals; refresh source data.")
        standings = official[STANDING_COLUMNS]
    rows = []
    for team in official["team"]:
        own_league = team_leagues.get(team)
        games = history[history["homeTeam"].eq(team) | history["awayTeam"].eq(team)]
        domestic = games[~games["competition"].isin(EUROPEAN_COMPETITIONS)]
        current = domestic[domestic["season"].eq(season)]
        prior = domestic[~domestic["season"].eq(season)]
        european = games[games["competition"].isin(EUROPEAN_COMPETITIONS)]
        xg = domestic.dropna(subset=["home_xg", "away_xg"]) if {"home_xg", "away_xg"}.issubset(domestic.columns) else domestic.iloc[:0]
        latest = domestic["utcDate"].max()
        rows.append({"team": team, "league": own_league, "current_domestic_matches": len(current),
                     "prior_domestic_matches": len(prior), "european_matches": len(european), "xg_matches": len(xg),
                     "latest_domestic_result": latest.isoformat() if pd.notna(latest) else None,
                     "source": " | ".join(sorted(domestic["source"].unique())),
                     "stale_days": float((origin - latest).total_seconds() / 86400) if pd.notna(latest) else None,
                     "domestic_missing": domestic.empty, "european_fallback": domestic.empty and not european.empty,
                     "xg_missing": xg.empty, "sparse_domestic": len(domestic) < 20})
    metadata = {
        "season": season, "as_of": origin.isoformat(), "prior_seasons": prior_seasons,
        "history_matches": len(history), "display_names": display_names, "provider_team_ids": provider_ids,
        "sources": sorted(source_audits, key=lambda item: (item["competition"], item["season"])), "source_errors": errors,
        "source_versions": {"openfootball_europe": EUROPE_COMMIT, "openfootball_european_cups": EURO_CUPS_COMMIT},
        "standings_source": "official" if use_official else "reconstructed at forecast origin",
        "availability": "Date-only domestic/supplement results and xG available next UTC day; timed API/PFL results after kickoff plus three hours.",
        "relocated_venue_model": "Verified relocated Shakhtar, Dynamo Kyiv and Maccabi Tel-Aviv European home fixtures, plus Besiktas–Maccabi in Debrecen on 2024-11-28, use neutral rates; home-support effects are not estimated.",
        "venue_sources": VENUE_SOURCES,
        "domestic_reconciliation": "Slovak, Ukrainian and Azerbaijani official tables checked against parsed played and goal totals; discrepancies reported per source. Czech pinned schedules have incomplete 2025/26 coverage.",
    }
    return UCLInputs(fixtures.reset_index(drop=True), standings.reset_index(drop=True), history, team_leagues, pd.DataFrame(rows), metadata)
