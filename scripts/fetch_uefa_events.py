from datetime import datetime, timedelta, timezone
import json
import time

import requests

from fetch_espn_events import team_name
from fetch_match_events import write_json
from validate_site_data import validate_match_events, validate_payload


MATCHES = "https://match.uefa.com/v5/matches"
STATS = "https://matchstats.uefa.com/v1"


def find_match(matches, fixture):
    found = []
    for match in matches:
        if match["kickOffTime"]["date"] != fixture["kickoff"][:10]:
            continue
        teams = [match["homeTeam"], match["awayTeam"]]
        if all(team_name(fixture[key]) in {team_name(team["internationalName"]),
               *(team_name(names["EN"]) for names in team["translations"].values() if "EN" in names)}
               for key, team in zip(("home", "away"), teams)):
            found.append(match)
    if len(found) != 1:
        raise ValueError(f"unmapped: expected one UEFA match, found {len(found)}")
    match = found[0]
    if match["status"] != "FINISHED":
        raise ValueError("UEFA match is not final")
    score = [match["score"]["total"][side] for side in ("home", "away")]
    if score != fixture["score"]:
        raise ValueError(f"UEFA final score {score} differs from ours {fixture['score']}")
    return match


def downsample(value):
    cells = [int(cell or 0) for cell in value.split(",")]
    if len(cells) != 105 * 69 or any(cell < 0 for cell in cells):
        raise ValueError("invalid UEFA 105×69 heatmap")
    grid = [0] * (21 * 14)
    for i, cell in enumerate(cells):
        # UEFA is row-major, x fastest; the final y bin contains four rather than five rows.
        grid[(i // 105 // 5) * 21 + i % 105 // 5] += cell
    return grid


def derive_uefa(match, teams, players, lineups, fixture, fetched_at):
    if str(lineups["matchId"]) != match["id"]:
        raise ValueError("UEFA lineup identity differs from listing")
    team_stats = {str(row["teamId"]): {s["name"]: s for s in row["statistics"]} for row in teams}
    physical, heat, positions = {}, {}, {}
    for side, key in (("h", "homeTeam"), ("a", "awayTeam")):
        team_id = match[key]["id"]
        lineup = lineups[key]
        if str(lineup["team"]["id"]) != team_id:
            raise ValueError("UEFA lineup team differs from listing")
        roster = {row["player"]["id"]: row for row in lineup["field"] + lineup["bench"]}
        starters = {row["player"]["id"] for row in lineup["field"]}
        stats = team_stats[team_id]
        physical[side] = {"distance": round(float(stats["distance_covered"]["value"]), 3),
                          "sprints": int(float(stats["sprints"]["value"])),
                          "top_speed": round(float(stats["top_speed"]["value"]), 3), "players": []}
        heat[side] = {"team": [0] * 294, "players": []}
        positions[side] = []
        for row in players:
            if str(row["teamId"]) != team_id:
                continue
            stats = {s["name"]: s for s in row["statistics"]}
            seconds = float(stats.get("played_time", {}).get("attributes", {}).get("TotalSeconds", 0))
            if seconds <= 0:
                continue
            player_id = str(row["playerId"])
            person = roster[player_id]
            identity = {"id": int(player_id), "player": person["player"]["internationalName"]}
            physical[side]["players"].append({**identity, "minutes": round(seconds / 60, 1),
                "distance": round(float(stats["distance_covered"]["value"]), 3),
                "top_speed": round(float(stats["top_speed"]["value"]), 3)})
            grid = downsample(stats["player_heatmap_105x69"]["value"])
            heat[side]["team"] = [a + b for a, b in zip(heat[side]["team"], grid)]
            if seconds >= 30 * 60:
                heat[side]["players"].append({"id": int(player_id), "grid": grid})
            if player_id in starters:
                # Average locations are centimetres from the centre; convert to the heatmap's top-left origin.
                x, y = map(float, stats["average_player_position"]["value"].split(","))
                positions[side].append({**identity, "number": person["jerseyNumber"],
                                       "x": round((x / 100 + 52.5) / 105, 4),
                                       "y": round((34.5 - y / 100) / 69, 4)})
    data = {"id": fixture["id"], "competition": fixture["competition"], "kickoff": fixture["kickoff"],
            "sources": {"uefa": {"id": int(match["id"]), "fetched_at": fetched_at, "score": fixture["score"]}},
            "physical": physical, "heat": heat, "positions": positions}
    validate_payload(data, "match_events")
    validate_match_events(data, fixture)
    return data


def fetch_uefa_events(src, data_dir, cache_dir):
    if not (src / "cl_match_forecasts.json").exists():
        return  # retained competition
    now = datetime.now(timezone.utc)
    try:
        fixtures = json.loads((data_dir / "matches/champions-league.json").read_text())["matches"]
        season = json.loads((data_dir / "champions-league.json").read_text())["season"][:4]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"WARNING: UEFA: {exc}")
        return
    fetched, mapped, published, total = 0, 0, 0, 0
    last_request = 0.0
    loaded = {}
    with requests.Session() as session:
        session.headers.update({"User-Agent": "Mozilla/5.0"})

        def raw(path, url, retry=False):
            nonlocal fetched, last_request
            if path not in loaded:
                cached = json.loads(path.read_text()) if path.exists() else None
                if not cached or cached.get("failed") or retry:
                    time.sleep(max(0, 1 - (time.monotonic() - last_request)))
                    last_request = time.monotonic()
                    fetched += 1
                    cached = {"fetched_at": datetime.now(timezone.utc).isoformat(), "failed": True}
                    write_json(path, cached)
                    loaded[path] = cached
                    response = session.get(url, timeout=30, allow_redirects=False)
                    response.raise_for_status()
                    cached["payload"] = response.json()
                    cached.pop("failed")
                    write_json(path, cached)
                loaded[path] = cached
            cached = loaded[path]
            if cached.get("failed"):
                raise ValueError("UEFA request failed earlier in this run")
            return cached

        for row in fixtures:
            if row["status"] != "FINISHED":
                continue
            total += 1
            fixture = {**row, "competition": "champions-league"}
            try:
                path = data_dir / "match" / season / "champions-league" / f"{row['id']}.json"
                existing = json.loads(path.read_text()) if path.exists() else {}
                if "uefa" in existing.get("sources", {}):
                    mapped += 1
                    continue
                attempt = cache_dir / "fixtures" / season / f"{row['id']}.json"
                failed = attempt.exists()
                if failed and now > datetime.fromisoformat(row["kickoff"]) + timedelta(days=7):
                    raise ValueError("unmapped/unpublished: retry window expired")
                write_json(attempt, {"failed": True, "fetched_at": now.isoformat()})
                # Refresh the season listing once per run when a new match needs ingestion.
                listing = raw(cache_dir / "matches" / f"{season}.json",
                              f"{MATCHES}?competitionId=1&seasonYear={int(season) + 1}&offset=0&limit=500", retry=True)
                match = find_match(listing["payload"], fixture)
                mapped += 1
                match_id = match["id"]
                teams = raw(cache_dir / "team" / f"{match_id}.json", f"{STATS}/team-statistics/{match_id}", failed)
                players = raw(cache_dir / "player" / f"{match_id}.json", f"{STATS}/player-statistics/{match_id}", failed)
                lineups = raw(cache_dir / "lineups" / f"{match_id}.json", f"{MATCHES}/{match_id}/lineups", failed)
                derived = derive_uefa(match, teams["payload"], players["payload"], lineups["payload"], fixture,
                                      max(item["fetched_at"] for item in (listing, teams, players, lineups)))
                merged = {**existing, **derived, "sources": {**existing.get("sources", {}), **derived["sources"]}}
                validate_payload(merged, "match_events")
                validate_match_events(merged, fixture)
                write_json(path, merged)
                attempt.unlink()
                published += 1
            except (requests.RequestException, OSError, ValueError, KeyError, TypeError, IndexError) as exc:
                print(f"WARNING: UEFA match {row['id']} ({row['kickoff'][:10]} {row['home']} v {row['away']}): {exc}")
    sizes = [(path.stat().st_size, path) for path in (data_dir / "match" / season / "champions-league").glob("*.json")]
    largest = f"; largest file: {max(sizes)[1].name}, {max(sizes)[0]:,} bytes" if sizes else ""
    print(f"UEFA: {fetched} requests, {published} match files published; season: {mapped}/{total} score-checked mappings{largest}")
