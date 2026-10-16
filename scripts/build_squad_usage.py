import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path

from build_squads import ROOT, load_players, sha256, write_json
from standing_prediction.lineup_usage import identify_appearance
from standing_prediction.squads import select_xi
from validate_site_data import COMPETITIONS, validate_payload


def match_sheet(detail, side, source):
    if source not in detail.get("sources", {}):
        return None
    if source == "understat":
        rows = detail.get("players", {}).get(side)
        if rows is None:
            return None
        return [{"source_id": row["id"], "name": row["player"], "minutes": row["minutes"],
                 "starter": row["position"] != "Sub"} for row in rows]
    physical = detail.get("physical", {}).get(side)
    positions = detail.get("positions", {}).get(side)
    if physical is None or positions is None:
        return None
    starters = {row["id"]: row for row in positions}
    observed = {row["id"]: row for row in physical["players"]}
    if (len(positions) != 11 or len(starters) != 11 or not starters.keys() <= observed.keys() or
            any(row["player"] != observed[pid]["player"] for pid, row in starters.items())):
        return []
    rows = []
    for row in physical["players"]:
        position = starters.get(row["id"])
        item = {"source_id": row["id"], "name": row["player"], "minutes": row["minutes"],
                "starter": position is not None}
        if position:
            # Both sides attack toward increasing x; y=0 is the player's left.
            item.update(avg_x=position["x"] if side == "h" else round(1 - position["x"], 4),
                        avg_y=position["y"] if side == "h" else round(1 - position["y"], 4))
        rows.append(item)
    return rows


def valid_sheet(rows):
    return (sum(row["starter"] for row in rows) == 11 and
            len({row["source_id"] for row in rows}) == len(rows) and all(
                isinstance(row["minutes"], (int, float)) and not isinstance(row["minutes"], bool) and
                math.isfinite(row["minutes"]) and 0 <= row["minutes"] <= 130 for row in rows))


def competition_usage(club, sheets, source):
    players = club["players"]
    ideal = {slot["player"] for slot in club["ideal_xi"]["slots"] if slot["player"] is not None}
    games, bindings = [], defaultdict(set)
    for fixture, detail, digest, side in sheets:
        rows = match_sheet(detail, side, source)
        reason = "missing_match_sheet" if rows is None else "invalid_match_sheet" if not valid_sheet(rows) else None
        mapped = []
        if reason is None:
            for row in rows:
                pid = identify_appearance(row["name"], players)
                mapped.append({**row, "player": pid})
                if pid is not None:
                    bindings[row["source_id"]].add(pid)
        games.append({"fixture_id": fixture["id"], "kickoff": fixture["kickoff"],
                      "opponent_id": fixture["away_id" if side == "h" else "home_id"],
                      "status": "missing" if rows is None else "partial", "reason": reason,
                      "sheet_sha256": digest, "appearances": mapped})
    for game in games:
        rows = game["appearances"]
        counts = Counter(row["player"] for row in rows if row["player"] is not None)
        for row in rows:
            if row["player"] is not None and (counts[row["player"]] > 1 or len(bindings[row["source_id"]]) > 1):
                row["player"] = None
        if game["reason"] is None:
            game["status"] = "complete" if all(row["player"] is not None for row in rows) else "partial"
            if game["status"] == "partial":
                game["reason"] = "unmapped_appearances"
        for key, starter in (("starters", True), ("subs", False)):
            game[key] = [row["player"] for row in rows if row["player"] is not None and row["starter"] == starter]
        known = set(game["starters"] + game["subs"])
        game["ideal_started"] = (len(ideal & set(game["starters"])) if len(ideal) == 11 and
                                 (game["status"] == "complete" or ideal <= known) else None)
    covered = sum(game["reason"] in (None, "unmapped_appearances") for game in games)
    totals = {}
    for player in players:
        pid = player["id"]
        observed = [row for game in games for row in game["appearances"] if row["player"] == pid]
        known = sum(game["status"] == "complete" or any(row["player"] == pid for row in game["appearances"])
                    for game in games)
        minutes = round(sum(row["minutes"] for row in observed), 1) if known else None
        total = {"starts": sum(row["starter"] for row in observed) if known else None,
                 "sub": sum(not row["starter"] for row in observed) if known else None,
                 "minutes": minutes, "share": round(minutes / (90 * covered), 6) if known and covered else None,
                 "known_games": known, "unknown_games": len(games) - known,
                 "provider_ids": sorted({row["source_id"] for row in observed})}
        if source == "uefa":
            positions = [row for row in observed if "avg_x" in row]
            total.update(avg_x=round(sum(row["avg_x"] for row in positions) / len(positions), 4) if positions else None,
                         avg_y=round(sum(row["avg_y"] for row in positions) / len(positions), 4) if positions else None)
        totals[str(pid)] = total
    selection = select_xi(players, club["ideal_xi"]["formation"], minutes={int(pid): row["minutes"] for pid, row in totals.items()})
    return {"source": source, "games": len(games), "covered": covered,
            "fully_mapped": sum(game["status"] == "complete" for game in games), "players": totals,
            "most_used_xi": {"formation": selection["formation"], "status": selection["status"],
                             "slots": [{"role": slot["role"], "player": slot["player_id"]} for slot in selection["slots"]]},
            "games_list": games}


def build_usage(club, data_dir, ea_records):
    players = [{**row, "ea": {**ea_records[row["ea"]["id"]], "rating": row["ea"]["overall"],
                              "positions": row["ea"]["positions"]} if row["ea"] else None} for row in club["players"]]
    usage = {}
    for slug in COMPETITIONS:
        table = json.loads((data_dir / f"{slug}.json").read_text())
        if table["season"][:4] != club["season"] or club["club_id"] not in {row["id"] for row in table["teams"]}:
            continue
        fixtures = json.loads((data_dir / "matches" / f"{slug}.json").read_text())["matches"]
        fixtures = sorted((row for row in fixtures if row["status"] == "FINISHED" and
                           club["club_id"] in (row["home_id"], row["away_id"])), key=lambda row: (row["kickoff"], row["id"]))
        sheets = []
        for fixture in fixtures:
            path = data_dir / "match" / club["season"] / slug / f"{fixture['id']}.json"
            detail = json.loads(path.read_text()) if path.exists() else {}
            if detail and (detail["id"] != fixture["id"] or detail["competition"] != slug or detail["kickoff"] != fixture["kickoff"]):
                raise ValueError(f"Match identity differs: {path}")
            sheets.append((fixture, detail, sha256(path) if path.exists() else None,
                           "h" if fixture["home_id"] == club["club_id"] else "a"))
        usage[slug] = competition_usage({**club, "players": players}, sheets,
                                      "uefa" if slug == "champions-league" else "understat")
    return usage


def main(argv=None):
    parser = argparse.ArgumentParser(description="Add per-competition season participation from published match sheets.")
    parser.add_argument("--site-data", type=Path, default=ROOT / "site/data")
    parser.add_argument("--players", type=Path, default=ROOT / ".cache/players/ea/fc27-2026-09-12.csv")
    args = parser.parse_args(argv)
    records, _ = load_players(args.players)
    ea_records = {row["id"]: row for row in records}
    digest = sha256(args.players)
    catalog = json.loads((args.site_data / "clubs.json").read_text())
    season = catalog["season"][:4]
    paths = sorted((args.site_data / "squads" / season).glob("*.json"))
    if {path.stem for path in paths} != {club["slug"] for club in catalog["clubs"]}:
        raise ValueError("Squad files differ from the club catalog; refusing partial season usage.")
    pending = []
    for path in paths:
        club = json.loads(path.read_text())
        if club["ratings"]["sha256"] != digest:
            raise ValueError(f"EA aliases differ from frozen squad input: {path}")
        usage = build_usage(club, args.site_data, ea_records)
        if club.get("usage") != usage:
            club.update(usage=usage, usage_generated_at=datetime.now(timezone.utc).isoformat())
            pending.append((path, club))
        validate_payload(club, "squad")
    for path, club in pending:
        write_json(path, club)
    print(f"Squad usage: {len(pending)} files updated; frozen EA baselines unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
