import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import time

import requests

from validate_site_data import COMPETITIONS, validate_match_events, validate_payload


def goal_distribution(xgs):
    probabilities = [1.0]
    for xg in xgs:
        next_probs = [0.0] * (len(probabilities) + 1)
        for goals, probability in enumerate(probabilities):
            next_probs[goals] += probability * (1 - xg)
            next_probs[goals + 1] += probability * xg
        probabilities = next_probs
    return probabilities


def retrospective(shots):
    home, away = (goal_distribution(shot[4] for shot in shots if shot[1] == side and shot[5] != "OwnGoal")
                  for side in ("h", "a"))
    outcomes = [0.0, 0.0, 0.0]
    for h, p_home in enumerate(home):
        for a, p_away in enumerate(away):
            outcomes[0 if h > a else 1 if h == a else 2] += p_home * p_away
    return outcomes


def derive(payload, fixture, understat_id, fetched_at):
    shots, players = [], {}
    for side in ("h", "a"):
        for shot in payload["shots"][side]:
            if int(shot["match_id"]) != understat_id or shot["h_a"] != side:
                raise ValueError("shot identity differs from requested match or side")
            shots.append([int(shot["minute"]), side, float(shot["X"]), float(shot["Y"]), float(shot["xG"]),
                          shot["result"], shot["situation"], shot["shotType"], shot["player"], shot["player_assisted"],
                          shot.get("lastAction")])
        players[side] = [{
            "id": int(row["player_id"]), "player": row["player"], "minutes": int(row["time"]),
            "position": row["position"], "shots": int(row["shots"]), "goals": int(row["goals"]),
            "own_goals": int(row["own_goals"]), "xg": float(row["xG"]), "xa": float(row["xA"]),
            "key_passes": int(row["key_passes"]), "yellow": int(row["yellow_card"]), "red": int(row["red_card"]),
        } for row in payload["rosters"][side].values()]
    shots.sort(key=lambda shot: shot[0])
    data = {
        "id": fixture["id"], "competition": fixture["competition"], "kickoff": fixture["kickoff"],
        "sources": {"understat": {"id": understat_id, "fetched_at": fetched_at}},
        "shots": shots, "players": players, "retro": retrospective(shots),
    }
    validate_payload(data, "match_events")
    validate_match_events(data, fixture)
    return data


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def fetch_events(src, data_dir, cache_dir):
    now = datetime.now(timezone.utc)
    last_request = 0.0
    fetched, published = 0, 0
    with requests.Session() as session:
        session.headers.update({"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"})
        for slug, code in COMPETITIONS.items():
            if code == "CL":
                continue
            source = src / f"{code.lower()}_match_forecasts.json"
            if not source.exists():
                continue
            try:
                forecasts = json.loads(source.read_text())
                matches = json.loads((data_dir / "matches" / f"{slug}.json").read_text())
                fixtures = {row["id"]: row for row in matches["matches"]}
                season = str(int(forecasts["season"]))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                print(f"WARNING: {slug}: {exc}")
                continue
            for row in forecasts["matches"]:
                if row["status"] != "FINISHED" or row.get("understat_id") is None:
                    continue
                try:
                    fixture = {**fixtures[row["id"]], "competition": slug}
                    if fixture["status"] != "FINISHED" or fixture["kickoff"] != row["utcDate"]:
                        raise ValueError("published fixture differs from model output")
                    path = data_dir / "match" / season / slug / f"{fixture['id']}.json"
                    existing = json.loads(path.read_text()) if path.exists() else {}
                    # Files derived before shots kept Understat's last action are derived once more.
                    if "understat" in existing.get("sources", {}) and all(len(shot) == 11 for shot in existing.get("shots", [])):
                        continue
                    understat_id = int(row["understat_id"])
                    cache_path = cache_dir / f"{understat_id}.json"
                    cached = json.loads(cache_path.read_text()) if cache_path.exists() else None
                    kickoff = datetime.fromisoformat(fixture["kickoff"])
                    if cached and cached.get("failed") and now > kickoff + timedelta(days=7):
                        continue
                    if not cached or cached.get("failed"):
                        time.sleep(max(0, 1 - (time.monotonic() - last_request)))
                        last_request = time.monotonic()
                        fetched += 1
                        cached = {"fetched_at": datetime.now(timezone.utc).isoformat(), "failed": True}
                        write_json(cache_path, cached)
                        response = session.get(f"https://understat.com/getMatchData/{understat_id}",
                                               timeout=30, allow_redirects=False)
                        response.raise_for_status()
                        cached["payload"] = response.json()
                        write_json(cache_path, cached)
                    derived = derive(cached["payload"], fixture, understat_id, cached["fetched_at"])
                    merged = {**existing, **derived, "sources": {**existing.get("sources", {}), **derived["sources"]}}
                    validate_payload(merged, "match_events")
                    write_json(path, merged)
                    cached.pop("failed", None)
                    write_json(cache_path, cached)
                    published += 1
                except (requests.RequestException, OSError, ValueError, KeyError, TypeError) as exc:
                    print(f"WARNING: {slug} match {row['id']}: {exc}")
    print(f"Understat: {fetched} requests, {published} match files published")


def main():
    parser = argparse.ArgumentParser(description="Fetch finished match detail once, without changing forecasts.")
    parser.add_argument("--src", type=Path, default=Path("out/site"))
    parser.add_argument("--data", type=Path, default=Path("site/data"))
    parser.add_argument("--cache", type=Path, default=Path(".cache/understat/matches"))
    parser.add_argument("--espn-cache", type=Path, default=Path(".cache/espn/matches"))
    parser.add_argument("--uefa-cache", type=Path, default=Path(".cache/uefa"))
    parser.add_argument("--provider", choices=("all", "understat", "espn", "uefa"), default="all")
    args = parser.parse_args()
    if args.provider in ("all", "understat"):
        fetch_events(args.src, args.data, args.cache)
    if args.provider in ("all", "espn"):
        from fetch_espn_events import fetch_espn_events
        if args.provider == "all":
            time.sleep(1)
        fetch_espn_events(args.src, args.data, args.espn_cache)

    if args.provider in ("all", "uefa"):
        from fetch_uefa_events import fetch_uefa_events
        if args.provider == "all":
            time.sleep(1)
        fetch_uefa_events(args.src, args.data, args.uefa_cache)


if __name__ == "__main__":
    main()
