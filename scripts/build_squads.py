import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import pandas as pd
from dotenv import load_dotenv

from standing_prediction.data import FootballDataClient
from standing_prediction.squads import FORMATIONS, birth_date, match_squads, player_index, select_xi


ROOT = Path(__file__).resolve().parents[1]
COMPETITIONS = {"PD": "la-liga", "PL": "premier-league", "BL1": "bundesliga", "SA": "serie-a",
                "FL1": "ligue-1", "CL": "champions-league"}
EA_SOURCE = "https://raw.githubusercontent.com/LakshmiKanth11/EA_FC_ANALYSIS/c0b2542d9fcae72d2c538a472a30ee57c4e7c75e/EA_FC_PLAYERS_DATASET_AND_%20DASHBOARD/data/players.csv"


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def sha256(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def ea_date(value):
    return birth_date(value) or datetime.strptime(value, "%d-%m-%Y").date().isoformat()


def load_players(path):
    frame = pd.read_csv(path, dtype=str).fillna("")
    required = {"player_id", "first_name", "last_name", "common_name", "birthdate", "overall_rating", "position",
                "alternate_positions", "club", "gender", "edition", "snapshot_date"}
    if not required <= set(frame):
        raise ValueError(f"EA CSV missing columns: {sorted(required - set(frame))}")
    editions = set(frame.edition)
    snapshots = {ea_date(value) for value in frame.snapshot_date}
    if len(editions) != 1 or len(snapshots) != 1:
        raise ValueError("Use one EA edition and snapshot per baseline; do not mix rating scales or vintages.")
    records = []
    for row in frame[frame.gender.eq("Men's Football")].itertuples():
        rating = int(row.overall_rating) if row.overall_rating.isdigit() else None
        records.append({"id": int(row.player_id), "name": f"{row.first_name} {row.last_name}".strip(),
                        "common_name": row.common_name, "dob": ea_date(row.birthdate),
                        "rating": rating if rating is not None and 1 <= rating <= 99 else None,
                        "positions": list(dict.fromkeys(re.findall(r"[A-Z]+", row.position + " " + row.alternate_positions))),
                        "dataset_club": row.club})
    if not records:
        raise ValueError("EA CSV has no men's player records.")
    return records, {"edition": next(iter(editions)), "snapshot_date": next(iter(snapshots))}


def rosters(code, cache, offline):
    if cache.exists():
        return json.loads(cache.read_text())
    if offline:
        raise ValueError(f"Missing roster snapshot: {cache}")
    payload = FootballDataClient(use_cache=False).get(f"/competitions/{code}/teams")
    data = {"fetched_at": datetime.now(timezone.utc).isoformat(),
            "url": f"https://api.football-data.org/v4/competitions/{code}/teams", "payload": payload}
    write_json(cache, data)
    return data


def freeze_baseline(data, out):
    encoded = json.dumps(data, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    baseline_id = hashlib.sha256(encoded).hexdigest()[:16]
    path = out / "snapshots" / data["competition"] / f"{baseline_id}.json"
    if path.exists():
        saved = json.loads(path.read_text())
        if {key: value for key, value in saved.items() if key not in {"baseline_id", "created_at"}} != data:
            raise ValueError(f"Frozen baseline differs from its content hash: {path}")
        return saved
    data = {**data, "baseline_id": baseline_id, "created_at": datetime.now(timezone.utc).isoformat()}
    write_json(path, data)
    return data


def report(data):
    coverage = data["coverage"]
    lines = [f"# {data['name']} ideal XIs", "",
             f"Baseline {data['baseline_id']}, frozen {data['created_at']}. Season {data['season']}.",
             f"EA {data['dataset']['edition']} ratings snapshot: {data['dataset']['snapshot_date']}. "
             f"Squads observed: {data['roster']['fetched_at']}.", "",
             f"Matched {coverage['matched']} of {coverage['players']} players across {coverage['clubs']} clubs.", "",
             "Each XI maximizes summed EA overall rating in the chosen formation, using primary and alternative "
             "positions. LW/LM and RW/RM are compatible wide roles. Everyone is assumed available; this is a "
             "rating-based reference, not a predicted lineup or a match-probability adjustment. "
             "Unmatched squad members can still change a provisional XI.", "",
             "| Club | Matched / squad | XI | Mean overall |", "| --- | ---: | --- | ---: |"]
    for club in data["clubs"]:
        xi = club["best_xi"]
        lines.append(f"| {club['name']} | {club['coverage']['matched']} / {len(club['players'])} | "
                     f"{xi['status']} | {xi['mean_rating'] or '—'} |")
    for club in data["clubs"]:
        xi = club["best_xi"]
        players = {row["id"]: row for row in club["players"]}
        lines.extend(["", f"## {club['name']}", "", f"{xi['formation']} · {xi['status']}", "",
                      "| Role | Player | Overall |", "| --- | --- | ---: |"])
        for slot in xi["slots"]:
            player = players.get(slot["player_id"])
            lines.append(f"| {slot['role']} | {player['name'] if player else 'Unfilled'} | {slot['rating'] or '—'} |")
        unresolved = [row["name"] for row in club["players"] if row["status"] != "matched"]
        if unresolved:
            lines.extend(["", "Unmatched or ambiguous: " + ", ".join(unresolved) + "."])
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Match supported squads to EA ratings and freeze position-constrained ideal XIs.")
    parser.add_argument("--players", type=Path, default=ROOT / ".cache/players/ea/fc27-2026-09-12.csv")
    parser.add_argument("--source-url", help="Provenance URL when using a different EA CSV")
    parser.add_argument("--competition", nargs="+", choices=COMPETITIONS, default=["PD"])
    parser.add_argument("--formation", choices=FORMATIONS, default="4-3-3")
    parser.add_argument("--site-data", type=Path, default=ROOT / "site/data")
    parser.add_argument("--overrides", type=Path, default=ROOT / "data/players/identity_overrides.json")
    parser.add_argument("--roster-cache", type=Path, default=ROOT / ".cache/players/rosters")
    parser.add_argument("--roster-date", default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--out", type=Path, default=ROOT / "out/squads")
    args = parser.parse_args(argv)
    if args.roster_date != datetime.now(timezone.utc).date().isoformat() and not args.offline:
        parser.error("An older --roster-date requires --offline; current squads cannot reconstruct past squads.")
    records, metadata = load_players(args.players)
    overrides = json.loads(args.overrides.read_text())
    load_dotenv(ROOT / ".env")
    teams, sources = {}, {}
    for code in dict.fromkeys(args.competition):
        published = json.loads((args.site_data / f"{COMPETITIONS[code]}.json").read_text())
        cache = args.roster_cache / args.roster_date / f"{code}.json"
        source = rosters(code, cache, args.offline)
        payload = source["payload"]
        if payload["competition"]["code"] != code or payload["season"]["startDate"][:4] != published["season"][:4]:
            raise ValueError(f"{code}: roster competition/season differs from the published competition.")
        supported = {team["id"]: team for team in published["teams"]}
        found = {team["id"]: team for team in payload["teams"] if team["id"] in supported}
        if found.keys() != supported.keys() or any(not team["squad"] for team in found.values()):
            raise ValueError(f"{code}: missing supported clubs or empty squads; refusing a partial roster.")
        for tid, team in found.items():
            if tid in teams and teams[tid]["squad"] != team["squad"]:
                raise ValueError(f"Conflicting squad snapshots for team {tid}.")
            teams[tid] = team
        source["sha256"] = sha256(cache)
        sources[code] = (published, source, supported)
    source_url = args.source_url or (EA_SOURCE if args.players == parser.get_default("players") else None)
    dataset = {"file": args.players.name, "sha256": sha256(args.players), "rows": len(records),
               "url": source_url, **metadata}
    clubs = {club["id"]: club for club in match_squads(list(teams.values()), player_index(records), overrides)}
    for club in clubs.values():
        club["best_xi"] = select_xi(club["players"], args.formation)
        club["coverage"] = dict(Counter(row["status"] for row in club["players"]))
        club["coverage"].setdefault("matched", 0)
    for code, (published, source, supported) in sources.items():
        selected = [{**clubs[tid], "slug": supported[tid]["slug"]} for tid in sorted(supported)]
        data = {"competition": code, "name": published["name"], "season": published["season"], "dataset": dataset,
                "method": "ea-position-assignment-v1", "identity_overrides_sha256": sha256(args.overrides),
                "roster": {key: source[key] for key in ("fetched_at", "url", "sha256")},
                "coverage": {"clubs": len(selected), "players": sum(len(c["players"]) for c in selected),
                             "matched": sum(c["coverage"]["matched"] for c in selected)}, "clubs": selected}
        data = freeze_baseline(data, args.out)
        write_json(args.out / f"{code}.json", data)
        (args.out / f"{code}.md").write_text(report(data), encoding="utf-8")
        print(f"{code}: {data['coverage']}, baseline {data['baseline_id']} -> {args.out / (code + '.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
