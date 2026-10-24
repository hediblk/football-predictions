"""Fetch ESPN's team xG for finished Champions League fixtures, for display only (Understat has no UCL)."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import requests

from build_site_data import short_name, write_json
from fetch_espn_events import LEAGUES, check_score, find_event

SITE = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{LEAGUES['champions-league']}"
CORE = f"https://sports.core.api.espn.com/v2/sports/soccer/leagues/{LEAGUES['champions-league']}"


def team_xg(payload):
    for category in payload.get("splits", {}).get("categories", []):
        for stat in category.get("stats", []):
            if stat["name"] == "expectedGoals" and stat.get("value") is not None:
                return round(float(stat["value"]), 2)
    return None


def fetch_ucl_xg(src, cache_dir):
    forecasts = json.loads((src / "cl_match_forecasts.json").read_text())
    display = forecasts.get("display_names", {})
    name = lambda team: short_name(display.get(team, team))
    last = 0.0
    fetched = 0

    def get(path, url, keep):
        # Cached payloads are final: a completed scoreboard or a team's published xG.
        nonlocal last, fetched
        if path.exists():
            return json.loads(path.read_text())["payload"]
        time.sleep(max(0, 1 - (time.monotonic() - last)))
        last = time.monotonic()
        fetched += 1
        response = requests.get(url, timeout=30, allow_redirects=False)
        response.raise_for_status()
        payload = response.json()
        if keep(payload):
            write_json(path, {"fetched_at": datetime.now(timezone.utc).isoformat(), "payload": payload})
        return payload

    found, total = {}, 0
    for match in forecasts["matches"]:
        if match["status"] != "FINISHED":
            continue
        total += 1
        fixture = {"kickoff": match["utcDate"], "home": name(match["homeTeam"]), "away": name(match["awayTeam"]),
                   "score": [int(match["homeGoals"]), int(match["awayGoals"])]}
        try:
            date = fixture["kickoff"][:10].replace("-", "")
            board = get(cache_dir / "scoreboards" / f"{date}.json", f"{SITE}/scoreboard?dates={date}",
                        lambda b: all(e["competitions"][0]["status"]["type"]["completed"] for e in b["events"]))
            event = find_event(board, fixture)
            sides = check_score(event, fixture)
            xg = [team_xg(get(cache_dir / "teams" / f"{event['id']}-{side['id']}.json",
                              f"{CORE}/events/{event['id']}/competitions/{event['id']}/competitors/{side['id']}/statistics",
                              lambda p: team_xg(p) is not None)) for side in sides]
            if None in xg:
                raise ValueError("ESPN has no team xG")
            found[str(match["id"])] = {"espn": int(event["id"]), "xg": xg}
        except (requests.RequestException, OSError, ValueError, KeyError, TypeError, IndexError) as exc:
            print(f"WARNING: ESPN xG match {match['id']} ({fixture['kickoff'][:10]} {fixture['home']} v {fixture['away']}): {exc}")
    write_json(src / "cl_espn_xg.json", {"source": "espn", "matches": found})
    print(f"ESPN UCL xG: {fetched} requests, {len(found)}/{total} finished fixtures")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, default=Path("out/site"))
    parser.add_argument("--cache", type=Path, default=Path(".cache/espn/ucl-xg"))
    args = parser.parse_args()
    if not (args.src / "cl_match_forecasts.json").exists():
        print("No Champions League forecasts; skipping ESPN xG")
        return
    fetch_ucl_xg(args.src, args.cache)


if __name__ == "__main__":
    main()
