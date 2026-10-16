import argparse
import csv
from datetime import datetime, timezone
import fcntl
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import time

import requests


LEAGUES = ("EPL", "La_liga", "Bundesliga", "Serie_A", "Ligue_1")
PLAYER_FIELDS = (
    "match_id", "date", "side", "team", "player_id", "name", "position", "minutes",
    "appearance", "roster_id", "roster_in", "roster_out", "goals", "shots", "xg", "xa",
    "key_passes", "yellow_cards", "red_cards", "fetched_at",
)
TEAM_FIELDS = ("league", "season", "match_id", "date", "side", "team", "opponent", "xg_for", "xg_against",
               "league_xg_for", "league_xg_against")
EXCLUSION_FIELDS = ("league", "season", "match_id", "date", "reason", "fetched_at")
XG_TOLERANCE = 0.001


def write_bytes(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == content:
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def write_csv(path, fields, rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    content = output.getvalue().encode("utf-8")
    if path.suffix == ".gz":
        content = gzip.compress(content, mtime=0)
    write_bytes(path, content)


def league_inputs(cache):
    inputs = []
    seen = set()
    for league in LEAGUES:
        for season in range(2014, 2026):
            url = f"https://understat.com/getLeagueData/{league}/{season}"
            key = hashlib.sha256(json.dumps([url, {}], sort_keys=True).encode()).hexdigest()
            path = cache / f"{key}.json"
            cached = json.loads(path.read_text())
            payload = json.loads(cached["content"])
            matches = sorted((m for m in payload["dates"] if m.get("isResult")),
                             key=lambda m: (m["datetime"], int(m["id"])))
            for match in matches:
                match_id = int(match["id"])
                if match_id in seen:
                    raise ValueError(f"duplicate league match ID: {match_id}")
                seen.add(match_id)
            inputs.append((league, season, matches, {
                "league": league, "season": season, "url": url,
                "fetched_at": cached["fetched_at"],
                "sha256": hashlib.sha256(cached["content"].encode()).hexdigest(),
            }))
    return inputs


def derive(match, payload, fetched_at):
    rows = []
    seen = set()
    team_xgs = {}
    for side in ("h", "a"):
        roster = payload["rosters"][side]
        if not isinstance(roster, dict) or not roster:
            raise ValueError(f"{side}: missing roster")
        starters = 0
        for roster_id, player in roster.items():
            player_id = int(player["player_id"])
            if player_id <= 0 or player_id in seen:
                raise ValueError(f"duplicate or invalid player ID: {player_id}")
            seen.add(player_id)
            if (player["h_a"] != side or str(player["team_id"]) != str(match[side]["id"])
                    or str(player["id"]) != str(roster_id)):
                raise ValueError(f"{side}: roster identity mismatch")
            minutes = int(player["time"])
            if not 0 <= minutes <= 130:
                raise ValueError(f"{side}: minutes outside 0–130: {minutes}")
            if not player["position"] or not player["player"]:
                raise ValueError(f"{side}: missing player name or position")
            starter = player["position"] != "Sub"
            starters += starter
            row = {
                "match_id": int(match["id"]), "date": match["datetime"], "side": side,
                "team": match[side]["title"], "player_id": player_id, "name": player["player"],
                "position": player["position"], "minutes": minutes,
                "appearance": "starter" if starter else "substitute", "roster_id": int(roster_id),
                "roster_in": int(player["roster_in"]), "roster_out": int(player["roster_out"]),
                "goals": int(player["goals"]), "shots": int(player["shots"]),
                "xg": float(player["xG"]), "xa": float(player["xA"]),
                "key_passes": int(player["key_passes"]), "yellow_cards": int(player["yellow_card"]),
                "red_cards": int(player["red_card"]), "fetched_at": fetched_at,
            }
            for field in ("goals", "shots", "xg", "xa", "key_passes", "yellow_cards", "red_cards"):
                if not math.isfinite(row[field]) or row[field] < 0:
                    raise ValueError(f"{side}: invalid {field}")
            for link in ("roster_in", "roster_out"):
                if row[link] and str(row[link]) not in roster:
                    raise ValueError(f"{side}: unresolved {link}: {row[link]}")
            rows.append(row)
        if starters != 11:
            raise ValueError(f"{side}: {starters} starters, expected 11")
        shots = payload["shots"][side]
        for shot in shots:
            if (int(shot["match_id"]) != int(match["id"]) or shot["h_a"] != side
                    or shot["date"] != match["datetime"]
                    or shot["h_team"] != match["h"]["title"]
                    or shot["a_team"] != match["a"]["title"]):
                raise ValueError(f"{side}: shot match identity mismatch")
            if not math.isfinite(float(shot["xG"])) or not 0 <= float(shot["xG"]) <= 1:
                raise ValueError(f"{side}: invalid shot xG")
        team_xg = sum(float(shot["xG"]) for shot in shots if shot["result"] != "OwnGoal")
        team_xgs[side] = team_xg
        player_xg = sum(row["xg"] for row in rows if row["side"] == side)
        if not math.isfinite(team_xg) or team_xg < 0 or abs(player_xg - team_xg) > XG_TOLERANCE:
            raise ValueError(f"{side}: player xG {player_xg:.6f} != team xG {team_xg:.6f}")
    return rows, team_xgs


def export(inputs, cache, output):
    teams, exclusions, coverage = [], [], []
    for league, season, matches, _ in inputs:
        players, dates = [], []
        complete = pending = excluded = 0
        for match in matches:
            path = cache / f"{int(match['id'])}.json"
            if not path.exists():
                pending += 1
                continue
            fetched_at = ""
            try:
                cached = json.loads(path.read_text())
                fetched_at = cached["fetched_at"]
                dates.append(fetched_at)
                if cached.get("error"):
                    raise ValueError(cached["error"])
                payload = json.loads(cached["content"]) if "content" in cached else cached["payload"]
                match_players, team_xgs = derive(match, payload, fetched_at)
                players.extend(match_players)
            except (ValueError, KeyError, TypeError, OverflowError) as exc:
                exclusions.append(dict(zip(EXCLUSION_FIELDS, (
                    league, season, int(match["id"]), match["datetime"], str(exc), fetched_at,
                ))))
                excluded += 1
                continue
            complete += 1
            for side, other in (("h", "a"), ("a", "h")):
                teams.append(dict(zip(TEAM_FIELDS, (
                    league, season, int(match["id"]), match["datetime"], side,
                    match[side]["title"], match[other]["title"],
                    team_xgs[side], team_xgs[other],
                    float(match["xG"][side]), float(match["xG"][other]),
                ))))
        write_csv(output / league / f"{season}.csv.gz", PLAYER_FIELDS, players)
        coverage.append(f"| {league} | {season}/{str(season + 1)[2:]} | {len(matches)} | {complete} | "
                        f"{excluded} | {pending} | {min(dates) if dates else '—'} | "
                        f"{max(dates) if dates else '—'} |")
        print(f"{league} {season}: {complete}/{len(matches)} complete, {excluded} excluded, {pending} pending", flush=True)
    write_csv(output / "team_games.csv.gz", TEAM_FIELDS, teams)
    write_csv(output / "exclusions.csv", EXCLUSION_FIELDS, exclusions)
    write_bytes(output / "league_sources.json", (json.dumps(
        [item[3] for item in inputs], indent=2, ensure_ascii=False) + "\n").encode())
    readme = output / "README.md"
    template = readme if readme.exists() else Path(__file__).resolve().parents[1] / "data/players/understat/README.md"
    intro = template.read_text().split("<!-- coverage -->")[0]
    table = ("<!-- coverage -->\n\n| League | Season | Games | Complete sheets | Excluded | Pending | First fetch (UTC) | Last fetch (UTC) |\n"
             "| :--- | :--- | ---: | ---: | ---: | ---: | :--- | :--- |\n" + "\n".join(coverage) + "\n")
    write_bytes(readme, (intro + table).encode())
    return len(exclusions)


def run(args):
    inputs = league_inputs(args.league_cache)
    fetched = 0
    last_request = time.monotonic()
    with requests.Session() as session:
        session.headers.update({"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"})
        for league, season, matches, _ in inputs:
            before = fetched
            for match in matches:
                path = args.match_cache / f"{int(match['id'])}.json"
                if path.exists():
                    if not args.retry_failed or not json.loads(path.read_text()).get("error"):
                        continue
                if args.offline or (args.max_fetch is not None and fetched >= args.max_fetch):
                    continue
                time.sleep(max(0, 1 - (time.monotonic() - last_request)))
                last_request = time.monotonic()
                cached = {"fetched_at": datetime.now(timezone.utc).isoformat()}
                try:
                    response = session.get(f"https://understat.com/getMatchData/{int(match['id'])}",
                                           timeout=30, allow_redirects=False)
                    cached["content"] = response.text
                    if response.status_code != 200:
                        raise ValueError(f"HTTP {response.status_code}")
                    response.json()
                except (requests.RequestException, ValueError) as exc:
                    cached["error"] = str(exc)
                write_bytes(path, (json.dumps(cached, ensure_ascii=False) + "\n").encode())
                fetched += 1
                if fetched % 100 == 0:
                    print(f"Fetched {fetched}: {league} {season} match {match['id']}", flush=True)
            # Checkpoint after each season with new attempts.
            if fetched > before:
                export(inputs, args.match_cache, args.output)
    excluded = export(inputs, args.match_cache, args.output)
    print(f"Finished: {fetched} requests, {excluded} exclusions", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Archive historical Understat match sheets from cached league listings.")
    parser.add_argument("--league-cache", type=Path, default=Path(".cache/understat"))
    parser.add_argument("--match-cache", type=Path, default=Path(".cache/understat/matches"))
    parser.add_argument("--output", type=Path, default=Path("data/players/understat"))
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--max-fetch", type=int)
    args = parser.parse_args()
    if args.max_fetch is not None and args.max_fetch < 0:
        parser.error("--max-fetch must be nonnegative")
    args.match_cache.mkdir(parents=True, exist_ok=True)
    # A single archive writer also keeps concurrent invocations within the request limit.
    with (args.match_cache / ".rosters.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.exit(1, "Another roster archive run is active for this cache.\n")
        run(args)


if __name__ == "__main__":
    main()
