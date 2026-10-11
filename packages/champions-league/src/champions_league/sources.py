from __future__ import annotations

import io
import json
import re
from html import unescape

import pandas as pd

from standing_prediction.data import standings_from_matches
from standing_prediction.odds import fetch_football_data_uk_matches
from standing_prediction.utils import cache_max_age, cached_get

from champions_league.identities import COUNTRY_LEAGUES, canonical_team

EUROPE_COMMIT = "0bf83f88e8feb22904c5f9d93c6407574c1347e0"
EURO_CUPS_COMMIT = "abfaeddc2ee3d14f99ecc163c9ddb46cb4d67cef"
CSV_LEAGUES = {"PL": "E0", "PD": "SP1", "BL1": "D1", "SA": "I1", "FL1": "F1",
               "SC0": "SC0", "P1": "P1", "N1": "N1", "B1": "B1", "T1": "T1", "G1": "G1"}
COLUMNS = ["utcDate", "homeTeam", "awayTeam", "homeGoals", "awayGoals"]


def get_source(url, *, season=None, cache=True, params=None, pinned=False):
    return cached_get(url, params=params, cache_dir=".cache/ucl-sources" if cache else None,
                      max_age=None if pinned else cache_max_age(season))


def text(html):
    return " ".join(unescape(re.sub(r"<[^>]*>", " ", html)).split())


def frame(rows, *, source, season, league=None, date_only=False):
    out = pd.DataFrame(rows)
    if out.empty:
        out = pd.DataFrame(columns=COLUMNS)
    out["utcDate"] = pd.to_datetime(out["utcDate"], utc=True, errors="coerce")
    out["available_at"] = (out["utcDate"].dt.normalize() + pd.Timedelta(days=1)) if date_only else out["utcDate"] + pd.Timedelta(hours=3)
    for col in ["homeGoals", "awayGoals"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=COLUMNS).copy()
    out["season"], out["source"] = season, source
    out["neutral"] = out.get("neutral", False)
    out["competition"] = league
    if league:
        out["homeLeague"] = out["awayLeague"] = league
    out.attrs["source"] = source
    out.attrs["latest"] = out["utcDate"].max().isoformat() if not out.empty else None
    return out.reset_index(drop=True)


def reconcile(data, reported, source):
    if not reported:
        return {"source": source, "status": "unavailable", "reason": "No official table rows parsed."}
    matches = data.copy()
    for column in ["homeTeam", "awayTeam"]:
        matches[column] = matches[column].map(canonical_team)
    actual = standings_from_matches(matches).set_index("team")
    differences = []
    for name, expected in reported.items():
        name = canonical_team(name)
        if name not in actual.index:
            differences.append({"team": name, "missing": True})
            continue
        for column, value in expected.items():
            observed = int(actual.at[name, column])
            if observed != int(value):
                differences.append({"team": name, "column": column, "parsed": observed, "official": int(value)})
    return {"source": source, "status": "matched" if not differences else "mismatch", "clubs": len(reported), "differences": differences}


def csv_matches(league, season, *, cache=True):
    if league in CSV_LEAGUES:
        out = fetch_football_data_uk_matches(league_code=CSV_LEAGUES[league], season_start_year=season, use_cache=cache)
        url = f"https://www.football-data.co.uk/mmz4281/{season % 100:02d}{(season + 1) % 100:02d}/{CSV_LEAGUES[league]}.csv"
    else:
        url = f"https://www.football-data.co.uk/new/{league}.csv"
        data = pd.read_csv(io.StringIO(get_source(url, season=season, cache=cache)))
        wanted = str(season) if league == "NOR" else f"{season}/{season + 1}"
        data = data[data["Season"].astype(str).eq(wanted)].copy()
        out = data.rename(columns={"Home": "homeTeam", "Away": "awayTeam", "HG": "homeGoals", "AG": "awayGoals"})
        out["utcDate"] = pd.to_datetime(out["Date"], format="mixed", dayfirst=True, utc=True, errors="coerce")
    return frame(out.to_dict("records"), source=url, season=season, league=league, date_only=True)


def football_txt(content, *, season, source, competition, domestic_league=None):
    rows, date, month, year, final = [], None, 7, season, False
    months = dict(zip("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), range(1, 13)))
    for line in content.splitlines():
        if line.lstrip().startswith("▪"):
            final = bool(re.search(r"\bFinal\b", line, flags=re.I))
        stamp = re.match(r"\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\w{3})\s+(\d{1,2})(?:\s+(20\d{2}))?\s*$", line)
        if stamp:
            next_month = months[stamp[1]]
            if stamp[3]:
                year = int(stamp[3])
            else:
                year = season if next_month >= 7 else season + 1
            month = next_month
            date = pd.Timestamp(year=year, month=month, day=int(stamp[2]), tz="UTC")
            continue
        if date is None:
            continue
        value = re.sub(r"^\s*(?:\d{1,2}:\d{2}\s+)?", "", line)
        if domestic_league:
            match = re.match(r"(.+?)\s{2,}(\d+)-(\d+)(?:\s+\([^)]*\))?\s{2,}(.+?)\s*$", value)
            if not match:
                match = re.match(r"(.+?)\s+v\s+(.+?)\s{2,}(\d+)-(\d+)", value)
                if not match:
                    continue
                home, away, hg, ag = match.groups()
            else:
                home, hg, ag, away = match.groups()
            row = dict(zip(["homeTeam", "homeGoals", "awayGoals", "awayTeam"], [home, hg, ag, away]))
        else:
            match = re.match(r"(.+?)\s+\(([A-Z]{3})\)\s+v\s+(.+?)\s+\(([A-Z]{3})\)\s+(.*)", value)
            if not match:
                continue
            home, home_country, away, away_country, score = match.groups()
            if "a.e.t." in score:
                regular = re.search(r"a\.e\.t\.\s*\((\d+)-(\d+),", score)
                if regular is None:
                    raise ValueError(f"Missing regular-time score in {source}: {line.strip()}")
                hg, ag = regular.groups()
            else:
                regular = re.match(r"(\d+)-(\d+)", score)
                if regular is None:
                    continue
                hg, ag = regular.groups()
            row = {"homeTeam": home, "awayTeam": away, "homeGoals": hg, "awayGoals": ag,
                   "homeLeague": COUNTRY_LEAGUES.get(home_country, home_country),
                   "awayLeague": COUNTRY_LEAGUES.get(away_country, away_country), "neutral": final}
        row["utcDate"] = date
        rows.append(row)
    out = frame(rows, source=source, season=season, league=domestic_league, date_only=True)
    out["competition"] = competition
    if out.empty:
        raise ValueError(f"No scored fixtures parsed from {source}.")
    return out


def czech_matches(season, *, cache=True):
    url = f"https://raw.githubusercontent.com/openfootball/europe/{EUROPE_COMMIT}/czech-republic/{season}-{(season + 1) % 100:02d}_cz1.txt"
    return football_txt(get_source(url, cache=cache, pinned=True), season=season, source=url,
                        competition="CZ1", domestic_league="CZ1")


def european_supplement(*, cache=True):
    frames = []
    for filename, competition in [("el.txt", "EL"), ("conf.txt", "ECL")]:
        url = f"https://raw.githubusercontent.com/openfootball/champions-league/{EURO_CUPS_COMMIT}/2024-25/{filename}"
        frames.append(football_txt(get_source(url, cache=cache, pinned=True), season=2024, source=url, competition=competition))
    return frames


def slovak_matches(season, *, cache=True):
    base = f"https://www.nikeliga.sk/zapasy/{season}"
    index = get_source(base, season=season, cache=cache)
    stages = sorted(set(re.findall(r'id_stage=([123])(?:[&\"\s]|$)', index)))
    rows = []
    sources = []
    for stage in stages:
        url = f"{base}?id_round=999&id_stage={stage}"
        sources.append(url)
        page = get_source(url, season=season, cache=cache)
        table = re.search(r'<table class="schedule_table">(.*?)</table>', page, re.S)
        if table is None:
            raise ValueError(f"Missing Slovak fixture table for {season}.")
        for row in re.findall(r'<tr[^>]*>(.*?)</tr>', table[1], re.S):
            names = re.findall(r'<span class="schedule_table__team__name">(.*?)</span>', row, re.S)
            score = re.search(r'class="schedule_table__score"[^>]*>.*?>(\d+):(\d+)</a>', row, re.S)
            date = re.search(r'class="schedule_table__date--full">.*?(\d{1,2}\.\d{1,2}\.\d{4})', row, re.S)
            if len(names) == 2 and score and date:
                rows.append({"homeTeam": text(names[0]), "awayTeam": text(names[1]),
                             "homeGoals": score[1], "awayGoals": score[2],
                             "utcDate": pd.to_datetime(date[1], dayfirst=True, utc=True)})
    out = frame(rows, source=base, season=season, league="SK1", date_only=True)
    out.attrs["stage_urls"] = sources
    try:
        reported = {}
        for stage in (["2", "3"] if "2" in stages else ["1"]):
            table_url = f"https://www.nikeliga.sk/tabulka/{season}?id_stage={stage}"
            table_page = get_source(table_url, season=season, cache=cache)
            table = re.search(r'<table class="standings__table.*?</table>', table_page, re.S)
            for row in re.findall(r'<tr[^>]*>(.*?)</tr>', table[0] if table else "", re.S):
                name = re.search(r'<span class="hidden-xs">(.*?)</span>', row, re.S)
                values = re.findall(r'<td class="[^"<>]*\bnumber\b[^"<>]*">(-?\d+)</t[dh]>', row)
                if name and len(values) == 8:
                    reported[text(name[1])] = dict(zip(["played", "goals_for", "goals_against"], [values[0], values[4], values[5]]))
        out.attrs["reconciliation"] = reconcile(out, reported, f"https://www.nikeliga.sk/tabulka/{season}")
    except (RuntimeError, ValueError, KeyError) as exc:
        out.attrs["reconciliation"] = {"status": "unavailable", "error": str(exc)}
    if out.empty:
        raise ValueError(f"No Slovak results for {season}.")
    return out


def ukrainian_matches(season, *, cache=True):
    index = get_source("https://upl.ua/en/tournaments/championship/432/calendar", season=2026, cache=cache)
    seasons = {int(year): tournament for tournament, year in re.findall(r'<option value="(\d+)"[^>]*>(\d{4})/\d{2}</option>', index)}
    if season not in seasons:
        raise ValueError(f"UPL season {season} is absent from senior competition selector.")
    url = f"https://upl.ua/en/tournaments/championship/{seasons[season]}/calendar"
    page = get_source(url, season=season, cache=cache)
    rows, date = [], None
    pieces = re.split(r'(<div class="tour-date">.*?</div>)', page, flags=re.S)
    for piece in pieces:
        found = re.search(r'class="tour-date">(\d{2}\.\d{2}\.\d{4})', piece)
        if found:
            date = pd.to_datetime(found[1], dayfirst=True, utc=True)
            continue
        if date is None:
            continue
        matches = re.findall(r'<div class="team first-team">(.*?)<div class="resualt">(.*?)<div class="team second-team">(.*?)(?=<div class="tour-match">|<div class="table-tour|$)', piece, re.S)
        for home, result, away in matches:
            score = re.fullmatch(r"(\d+)\s+:\s+(\d+)", text(result))
            if score:
                rows.append({"homeTeam": text(home), "awayTeam": text(re.sub(r"^.*?</div>", "", away, count=1, flags=re.S).split("</div>")[0]),
                             "homeGoals": score[1], "awayGoals": score[2], "utcDate": date})
    out = frame(rows, source=url, season=season, league="UA1", date_only=True)
    try:
        table_url = url.replace("/calendar", "/table")
        table_page = get_source(table_url, season=season, cache=cache)
        table = re.search(r'<table class="table table-gray table-num">.*?</table>', table_page, re.S)
        reported = {}
        for row in re.findall(r'<tr[^>]*>(.*?)</tr>', table[0] if table else "", re.S):
            cells = [text(cell) for cell in re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)]
            if len(cells) == 10:
                name = re.search(r"«([^»]+)»", cells[1])
                reported[name[1] if name else cells[1]] = dict(zip(["played", "goals_for", "goals_against"], [cells[2], cells[6], cells[7]]))
        out.attrs["reconciliation"] = reconcile(out, reported, table_url)
    except (RuntimeError, ValueError, KeyError) as exc:
        out.attrs["reconciliation"] = {"status": "unavailable", "error": str(exc)}
    if out.empty:
        raise ValueError(f"No senior UPL results for {season}.")
    return out


def azerbaijan_matches(season, *, cache=True):
    index = json.loads(get_source("https://pfl.az/api/v1/seasons", season=2026, cache=cache, params={"project_id": 1}))
    selected = next((row for row in index["data"] if row["title"] == f"{season}-{season + 1}"), None)
    if selected is None:
        raise ValueError(f"PFL season {season} is unavailable.")
    league = next(row for row in selected["leagues"] if row["project"]["id"] == 1)
    url, rows, page = "https://pfl.az/api/v1/tours/get-games", [], 1
    while page:
        data = json.loads(get_source(url, season=season, cache=cache,
                                    params={"league_id": league["id"], "withGames": "true", "page": page}))
        for tour in data["data"]:
            if not str(tour["title"]).isdigit():
                continue
            for game in tour.get("games", []):
                if game["status"] != 3:
                    continue
                rows.append({"id": f"pfl-{game['id']}", "homeTeam": game["club_1"]["title"], "awayTeam": game["club_2"]["title"],
                             "homeGoals": game["club_score_1"], "awayGoals": game["club_score_2"],
                             "utcDate": pd.to_datetime(game["start_date"], format="%d/%m/%Y %H:%M").tz_localize("Asia/Baku").tz_convert("UTC")})
        page = page + 1 if data.get("next_page_url") else 0
    out = frame(rows, source=f"{url}?league_id={league['id']}&withGames=true", season=season, league="AZ1")
    try:
        table_url = f"https://pfl.az/api/v1/leagues/grid?season_id={selected['id']}&project_id=1"
        table = json.loads(get_source(table_url, season=season, cache=cache))["data"]
        reported = {club["title"]: dict(zip(["played", "goals_for", "goals_against"],
                    [club["rate"]["o"], club["rate"]["vq"], club["rate"]["bq"]])) for club in table}
        out.attrs["reconciliation"] = reconcile(out, reported, table_url)
    except (RuntimeError, ValueError, KeyError) as exc:
        out.attrs["reconciliation"] = {"status": "unavailable", "error": str(exc)}
    if out.empty:
        raise ValueError(f"No PFL results for {season}.")
    return out
