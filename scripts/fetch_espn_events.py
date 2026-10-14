from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import time

import requests

from standing_prediction.utils import normalize_team
from fetch_match_events import write_json
from validate_site_data import COMPETITIONS, validate_match_events, validate_payload


LEAGUES = {
    "premier-league": "eng.1", "la-liga": "esp.1", "bundesliga": "ger.1",
    "serie-a": "ita.1", "ligue-1": "fra.1", "champions-league": "uefa.champions",
}
OVERRIDES = json.loads(Path(__file__).with_name("espn_team_overrides.json").read_text())
STATS = {
    "possession": "possessionPct", "shots": "totalShots", "shots_on_target": "shotsOnTarget",
    "corners": "wonCorners", "fouls": "foulsCommitted", "offsides": "offsides", "saves": "saves",
    "yellow": "yellowCards", "red": "redCards",
}
EVENT_TYPES = {
    "goal": "goal", "own-goal": "own_goal", "penalty---scored": "penalty_goal",
    "penalty---missed": "missed_penalty", "yellow-card": "yellow", "red-card": "red",
    "penalty---saved": "missed_penalty", "penalty---hit-woodwork": "missed_penalty",
    "yellow-red-card": "red", "substitution": "substitution",
}


def team_name(name):
    name = normalize_team(name)
    return OVERRIDES.get(name, name)


def competitors(event):
    competition = event["competitions"][0]
    sides = {row["homeAway"]: row for row in competition["competitors"]}
    return competition, [sides["home"], sides["away"]]


def find_event(board, fixture):
    found = []
    for event in board["events"]:
        competition, sides = competitors(event)
        if competition["date"][:10] != fixture["kickoff"][:10]:
            continue
        if all(team_name(fixture[key]) in {team_name(row["team"][field]) for field in
               ("displayName", "shortDisplayName", "name") if row["team"].get(field)}
               for key, row in zip(("home", "away"), sides)):
            found.append(event)
    if len(found) != 1:
        raise ValueError(f"unmapped: expected one ESPN event, found {len(found)}")
    return found[0]


def check_score(event, fixture):
    competition, sides = competitors(event)
    if not competition["status"]["type"]["completed"]:
        raise ValueError("ESPN event is not final")
    score = [int(row["score"]) for row in sides]
    if score != fixture["score"]:
        raise ValueError(f"ESPN final score {score} differs from ours {fixture['score']}")
    return sides


def derive_espn(payload, fixture, event_id, fetched_at):
    header = payload["header"]
    if str(header["id"]) != str(event_id):
        raise ValueError("ESPN summary identity differs from scoreboard")
    # Recheck names, date and final score on the summary, not just the scoreboard.
    find_event({"events": [header]}, fixture)
    sides = check_score(header, fixture)
    side_ids = {str(row["id"]): side for side, row in zip(("h", "a"), sides)}
    statistics = {side_ids[str(row["team"]["id"])]: {
        stat["name"]: float(stat["displayValue"].rstrip("%")) for stat in row["statistics"]
        if stat["name"] in {*STATS.values(), "accuratePasses", "totalPasses"}
    } for row in payload["boxscore"]["teams"]}
    box = {key: [statistics[side][name] for side in ("h", "a")]
           for key, name in STATS.items() if all(name in statistics.get(side, {}) for side in ("h", "a"))}
    if all(statistics.get(side, {}).get("totalPasses", 0) > 0 and "accuratePasses" in statistics[side]
           for side in ("h", "a")):
        # ESPN's passPct is rounded to one decimal on 0–1; use counts for a useful percentage.
        box["pass_accuracy"] = [round(100 * statistics[side]["accuratePasses"] / statistics[side]["totalPasses"], 1)
                                for side in ("h", "a")]
    events = []
    for row in payload["keyEvents"]:
        kind = EVENT_TYPES.get(row["type"]["type"])
        if not kind and row.get("scoringPlay"):
            kind = "goal"  # headers, volleys and free kicks have their own ESPN type labels
        if not kind or row.get("shootout") or row.get("period", {}).get("number", 1) > 2:
            continue
        side = side_ids[str(row["team"]["id"])]
        # ESPN credits own goals to the beneficiary; our side identifies the participating player's team.
        if kind == "own_goal":
            side = "a" if side == "h" else "h"
        clock = re.findall(r"\d+", row["clock"]["displayValue"])
        if not clock:
            raise ValueError("ESPN event has no minute")
        events.append({"minute": sum(map(int, clock)), "clock": "+".join(clock), "type": kind, "side": side,
                       "players": [p["athlete"]["displayName"] for p in row["participants"]]})
    events.sort(key=lambda row: row["minute"])
    if not box:
        raise ValueError("ESPN box score is missing")
    data = {"id": fixture["id"], "competition": fixture["competition"], "kickoff": fixture["kickoff"],
            "sources": {"espn": {"id": int(event_id), "fetched_at": fetched_at, "score": fixture["score"]}},
            "box": box, "events": events}
    validate_payload(data, "match_events")
    validate_match_events(data, fixture)
    return data


def fetch_espn_events(src, data_dir, cache_dir):
    now = datetime.now(timezone.utc)
    monday = now.date() - timedelta(days=now.weekday())
    week_start = monday - timedelta(days=7)
    total, mapped, fetched, published = 0, 0, 0, 0
    last_request = 0.0
    loaded = {}
    with requests.Session() as session:
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
                    # Remember failures too: only one request per URL per run.
                    loaded[path] = cached
                    response = session.get(url, timeout=30, allow_redirects=False)
                    response.raise_for_status()
                    cached["payload"] = response.json()
                    cached.pop("failed")
                    write_json(path, cached)
                loaded[path] = cached
            cached = loaded[path]
            if cached.get("failed"):
                raise ValueError("ESPN request failed earlier in this run")
            return cached

        for slug, code in COMPETITIONS.items():
            if not (src / f"{code.lower()}_match_forecasts.json").exists():
                continue  # retained competition
            try:
                fixtures = json.loads((data_dir / "matches" / f"{slug}.json").read_text())["matches"]
                season = json.loads((data_dir / f"{slug}.json").read_text())["season"][:4]
            except (OSError, ValueError, KeyError, TypeError) as exc:
                print(f"WARNING: ESPN {slug}: {exc}")
                continue
            for row in fixtures:
                if row["status"] != "FINISHED":
                    continue
                recent = week_start.isoformat() <= row["kickoff"][:10] < monday.isoformat()
                total += recent
                fixture = {**row, "competition": slug}
                try:
                    path = data_dir / "match" / season / slug / f"{row['id']}.json"
                    existing = json.loads(path.read_text()) if path.exists() else {}
                    if "espn" in existing.get("sources", {}):
                        mapped += recent
                        continue
                    attempt = cache_dir / "fixtures" / slug / f"{row['id']}.json"
                    failed = attempt.exists()
                    if failed and now > datetime.fromisoformat(row["kickoff"]) + timedelta(days=7):
                        raise ValueError("unmapped/unpublished: retry window expired")
                    write_json(attempt, {"failed": True, "fetched_at": now.isoformat()})
                    base = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{LEAGUES[slug]}"
                    date = row["kickoff"][:10].replace("-", "")
                    board = raw(cache_dir / "scoreboards" / slug / f"{date}.json",
                                f"{base}/scoreboard?dates={date}", retry=failed)
                    event = find_event(board["payload"], fixture)
                    check_score(event, fixture)
                    summary = raw(cache_dir / "summaries" / f"{event['id']}.json",
                                  f"{base}/summary?event={event['id']}", retry=failed)
                    derived = derive_espn(summary["payload"], fixture, event["id"], summary["fetched_at"])
                    merged = {**existing, **derived, "sources": {**existing.get("sources", {}), **derived["sources"]}}
                    validate_payload(merged, "match_events")
                    write_json(path, merged)
                    attempt.unlink()
                    mapped += recent
                    published += 1
                except (requests.RequestException, OSError, ValueError, KeyError, TypeError, IndexError) as exc:
                    print(f"WARNING: ESPN {slug} match {row['id']} ({row['kickoff'][:10]} {row['home']} v {row['away']}): {exc}")
    coverage = f"{100 * mapped / total:.1f}%" if total else "no finished fixtures"
    print(f"ESPN: {fetched} requests, {published} match files published; last week ({week_start} to {monday - timedelta(days=1)}): {mapped}/{total} ({coverage}) score-checked mappings")
