import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
import html
import json
import math
from pathlib import Path

from build_squads import ROOT, load_players, sha256, write_json
from standing_prediction.lineup_usage import aliases, identify_appearance
from standing_prediction.squads import name_score, name_tokens, select_xi
from standing_prediction.utils import normalize_team
from validate_site_data import COMPETITIONS, validate_payload


def match_sheet(detail, side, source):
    if source not in detail.get("sources", {}):
        return None
    if source == "understat":
        rows = detail.get("players", {}).get(side)
        if rows is None:
            return None
        return [{"source_id": row["id"], "name": row["player"], "minutes": row["minutes"],
                 "starter": row["position"] != "Sub", "xg": row["xg"], "xa": row["xa"]} for row in rows]
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
    listed = [p for p in players if p["status"] != "observed"]
    extra = {pid: p["id"] for p in players if p["status"] == "observed"
             for pid in p["providers"].get(source, {}).get("ids", [])}
    ideal = {slot["player"] for slot in club["ideal_xi"]["slots"] if slot["player"] is not None}
    games, bindings = [], defaultdict(set)
    for fixture, detail, digest, side in sheets:
        rows = match_sheet(detail, side, source)
        reason = "missing_match_sheet" if rows is None else "invalid_match_sheet" if not valid_sheet(rows) else None
        mapped = []
        if reason is None:
            for row in rows:
                pid = extra.get(row["source_id"], identify_appearance(row["name"], listed))
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
                                 (game["status"] == "complete" or len(game["starters"]) == 11 or ideal <= known) else None)
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
        if source == "understat":
            # season xG and xA totals; per-90 rates are left to the reader
            total.update({key: round(sum(row[key] for row in observed), 4) if known else None for key in ("xg", "xa")})
        if source == "uefa":
            positions = [row for row in observed if "avg_x" in row]
            total.update(avg_x=round(sum(row["avg_x"] for row in positions) / len(positions), 4) if positions else None,
                         avg_y=round(sum(row["avg_y"] for row in positions) / len(positions), 4) if positions else None)
        totals[str(pid)] = total
    selection = select_xi(players, club["ideal_xi"]["formation"], minutes={p["id"]: totals[str(p["id"])]["minutes"] for p in players})
    return {"source": source, "games": len(games), "covered": covered,
            "fully_mapped": sum(game["status"] == "complete" for game in games), "players": totals,
            "most_used_xi": {"formation": selection["formation"], "status": selection["status"],
                             "slots": [{"role": slot["role"], "player": slot["player_id"]} for slot in selection["slots"]]},
            "games_list": games}


def observed_ea(names, club_name, ea_records):
    scored = []
    for ea in ea_records.values():
        scores = [name_score(name, [ea["name"], ea["common_name"]], appearance=True) for name in names]
        scores = [score for score in scores if score is not None]
        if scores:
            scored.append((min(scores), ea))
    local = [(score, ea) for score, ea in scored if normalize_team(ea["dataset_club"]) == normalize_team(club_name)]
    # Without the club, only an exact full or common name is safe (a surname subset found the wrong Ricardo Rodríguez).
    pool = local or [(score, ea) for score, ea in scored if score == 0]
    best = [ea for score, ea in pool if score == min(s for s, _ in pool)] if pool else []
    if len(best) != 1:
        return None, None, "ambiguous_name_match" if best else "no_name_match"
    return best[0], "name_and_club" if local else "unique_name", None


def possible_listed_alias(name, player):
    tokens = name_tokens(name)
    if not tokens:
        return True
    def compact(text):
        return "".join(sorted(name_tokens(text.replace("'", "").replace("’", "").replace("-", ""))))
    # A veto only: similar names never establish a new identity binding.
    for alias in filter(None, aliases(player)):
        if (name_score(name, [alias], appearance=True) is not None or
                name_tokens(name.split()[-1]) & name_tokens(alias) or name_tokens(alias.split()[-1]) & tokens or
                SequenceMatcher(None, compact(name), compact(alias)).ratio() >= 0.8):
            return True
    return False


def observed_players(club, usage, listed, ea_records):
    identities = defaultdict(list)
    for slug, cohort in usage.items():
        for game in cohort["games_list"]:
            for row in game["appearances"]:
                identities[cohort["source"], row["source_id"]].append((slug, game, row))
    groups, qualified = {}, set()
    for (source, sid), appearances in sorted(identities.items()):
        names = sorted({html.unescape(row["name"]) for _, _, row in appearances})
        # An ambiguous listed name or a provider ID already bound to the squad is not a new player.
        if (any(row["player"] is not None for _, _, row in appearances) or
                any(possible_listed_alias(name, p) for name in names for p in listed)):
            continue
        games = defaultdict(set)
        for slug, game, _ in appearances:
            games[slug].add(game["fixture_id"])
        ea, method, reason = observed_ea(names, club["name"], ea_records)
        # A listed player with the candidate's birth date may be a spelling/alias gap.
        # Leave that identity unresolved until a source-backed override settles it.
        if ea and any(p["dob"] == ea["dob"] for p in listed):
            continue
        # Multiple providers can observe the same player; numbers are scoped to their source.
        key = ("ea", ea["id"]) if ea else ("name", tuple(sorted(name_tokens(names[0]))))
        if max(map(len, games.values())) >= 2:
            qualified.add(key)
        dates = [game["kickoff"][:10] for _, game, _ in appearances]
        if key not in groups:
            groups[key] = {"id": f"observed:{source}:{sid}", "name": names[0], "dob": None,
                           "provider_position": None, "status": "observed", "source": "match_sheet",
                           "method": method,
                           "ea": ({"id": ea["id"], "overall": ea["rating"], **{k: ea[k] for k in
                                  ("positions", "pace", "shooting", "passing", "dribbling", "defending", "physical")}}
                                  if ea else None), "providers": {}, "first_seen": min(dates), "last_seen": max(dates)}
            if ea is None:
                groups[key]["reason"] = reason
        player = groups[key]
        provider = player["providers"].setdefault(source, {"ids": [], "names": []})
        provider["ids"].append(sid)
        provider["names"] = sorted(set(provider["names"]) | set(names))
        player["first_seen"] = min(player["first_seen"], min(dates))
        player["last_seen"] = max(player["last_seen"], max(dates))
    assigned = {p["ea"]["id"] for p in listed if p["ea"]}
    # Conflicting same-source identities stay unresolved; a listed EA identity is never duplicated.
    return [p for key, p in groups.items() if key in qualified and all(len(v["ids"]) == 1 for v in p["providers"].values()) and
            not (p["ea"] and p["ea"]["id"] in assigned)]


def build_usage(club, data_dir, ea_records):
    players = [{**row, "ea": {**ea_records[row["ea"]["id"]], "rating": row["ea"]["overall"],
                              "positions": row["ea"]["positions"]} if row["ea"] else None}
               for row in club["players"] if row["status"] != "observed"]
    usage, inputs = {}, {}
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
        source = "uefa" if slug == "champions-league" else "understat"
        inputs[slug] = (sheets, source)
        usage[slug] = competition_usage({**club, "players": players}, sheets, source)
    observed = observed_players(club, usage, players, ea_records)
    club["players"] = [p for p in club["players"] if p["status"] != "observed"] + observed
    if observed:
        players += [{**p, "ea": {**p["ea"], "rating": p["ea"]["overall"]} if p["ea"] else None} for p in observed]
        usage = {slug: competition_usage({**club, "players": players}, sheets, source)
                 for slug, (sheets, source) in inputs.items()}
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
        old_players = club["players"]
        usage = build_usage(club, args.site_data, ea_records)
        if club.get("usage") != usage or old_players != club["players"]:
            club.update(usage=usage, usage_generated_at=datetime.now(timezone.utc).isoformat())
            pending.append((path, club))
        validate_payload(club, "squad")
    for path, club in pending:
        write_json(path, club)
    print(f"Squad usage: {len(pending)} files updated; frozen EA baselines unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
