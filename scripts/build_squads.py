import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.request import urlopen

import pandas as pd
from dotenv import load_dotenv

from standing_prediction.data import FootballDataClient
from standing_prediction.squads import FORMATIONS, birth_date, match_player, match_squads, player_index, select_xi
from validate_site_data import validate_payload


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
                        "dataset_club": row.club,
                        **{key: int(getattr(row, column)) if getattr(row, column, "").isdigit() else None
                           for key, column in {"pace": "pace", "shooting": "shooting", "passing": "passing",
                                               "dribbling": "dribbling", "defending": "defending",
                                               "physical": "physicality"}.items()}})
    if not records:
        raise ValueError("EA CSV has no men's player records.")
    return records, {"edition": next(iter(editions)), "snapshot_date": next(iter(snapshots))}


def rosters(code, cache_dir, roster_date, offline, archive):
    cutoff = datetime.fromisoformat(roster_date).replace(tzinfo=timezone.utc) + timedelta(days=1)
    snapshots = []
    for directory in dict.fromkeys((cache_dir, archive)):
        for path in directory.glob(f"*/{code}.json"):
            data = json.loads(path.read_text())
            observed = datetime.fromisoformat(data["fetched_at"])
            if observed < cutoff:
                snapshots.append((observed, path, data))
    latest = max(snapshots, key=lambda row: row[0]) if snapshots else None
    now = datetime.now(timezone.utc)
    if latest and (offline or now - latest[0] < timedelta(days=7)):
        observed, path, data = latest
    else:
        if offline:
            raise ValueError(f"Missing roster snapshot: {code} at {roster_date}")
        payload = FootballDataClient(use_cache=False).get(f"/competitions/{code}/teams")
        observed = datetime.now(timezone.utc)
        data = {"fetched_at": observed.isoformat(),
                "url": f"https://api.football-data.org/v4/competitions/{code}/teams", "payload": payload}
        path = cache_dir / observed.date().isoformat() / f"{code}.json"
        if path.exists():
            raise ValueError(f"Refusing to replace roster observation: {path}")
        write_json(path, data)
        time.sleep(7)  # Leave room within football-data.org's ten requests per minute.
    archived = archive / observed.date().isoformat() / f"{code}.json"
    if archived.exists():
        if archived.read_bytes() != path.read_bytes():
            raise ValueError(f"Immutable roster differs: {archived}")
    else:
        archived.parent.mkdir(parents=True, exist_ok=True)
        archived.write_bytes(path.read_bytes())
    return {**data, "sha256": sha256(archived),
            "snapshot": f"data/players/rosters/{observed.date().isoformat()}/{code}.json"}


def publish_clubs(clubs, sources, dataset, args):
    catalog = json.loads((args.site_data / "clubs.json").read_text())["clubs"]
    overrides = json.loads(args.overrides.read_text())
    if set(clubs) != {club["id"] for club in catalog}:
        raise ValueError("Squad club set differs from clubs.json; publish all six competitions together.")
    pending = []
    for entry in catalog:
        club = clubs[entry["id"]]
        code = max((code for code, (_, _, supported) in sources.items() if club["id"] in supported),
                   key=lambda code: datetime.fromisoformat(sources[code][1]["fetched_at"]))
        published, source, _ = sources[code]
        season = published["season"][:4]
        players = []
        for row in club["players"]:
            player = {key: row[key] for key in ("id", "name", "dob", "provider_position", "status", "method")}
            player["ea"] = ({"id": row["ea"]["id"], "overall": row["ea"]["rating"],
                             **{key: row["ea"][key] for key in ("positions", "pace", "shooting", "passing",
                                                               "dribbling", "defending", "physical")}}
                            if row["ea"] else None)
            if "reason" in row:
                player["reason"] = row["reason"]
            if "identity_override" in row:
                player["identity_override"] = row["identity_override"]
            players.append(player)
        xi = club["best_xi"]
        # Hash only this club's reviewed exceptions, so an override elsewhere leaves its reference frozen.
        applied = {str(row["id"]): overrides[str(row["id"])] for row in club["players"] if str(row["id"]) in overrides}
        data = {"slug": entry["slug"], "club_id": club["id"], "name": club["name"], "season": season,
                "ratings": {"source": "EA SPORTS FC", **dataset},
                "roster": {"source": "football-data.org", "status": "available" if players else "unavailable",
                           "observed_at": source["fetched_at"],
                           **{key: source[key] for key in ("url", "sha256", "snapshot")}},
                "identity_overrides_sha256": hashlib.sha256(json.dumps(applied, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                "method": "ea-position-assignment-v1",
                "coverage": {"players": len(players), "matched": club["coverage"]["matched"]},
                "ideal_xi": {"formation": xi["formation"], "status": xi["status"],
                             "mean_overall": xi["mean_rating"],
                             "slots": [{"role": slot["role"], "player": slot["player_id"]} for slot in xi["slots"]]},
                "players": players}
        baseline_id = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()[:16]
        snapshot = args.baselines / season / entry["slug"] / f"{baseline_id}.json"
        if snapshot.exists():
            saved = json.loads(snapshot.read_text())
            if {key: value for key, value in saved.items() if key not in {"baseline_id", "generated_at"}} != data:
                raise ValueError(f"Frozen club baseline differs: {snapshot}")
            data = saved
        else:
            data.update(baseline_id=baseline_id, generated_at=datetime.now(timezone.utc).isoformat())
        path = args.site_data / "squads" / season / f"{entry['slug']}.json"
        if not players and path.exists():
            print(f"WARNING: {entry['slug']}: empty provider squad; retaining previous file.")
            continue
        if not players:
            print(f"WARNING: {entry['slug']}: provider returned an empty squad; publishing unavailable state.")
        validate_payload(data, "squad")
        pending.append((snapshot, path, data))
    # Nothing is published until every club has passed the shared contract checks.
    for snapshot, path, data in pending:
        if not snapshot.exists():
            write_json(snapshot, data)
        previous = json.loads(path.read_text()) if path.exists() else {}
        if previous.get("baseline_id") == data["baseline_id"]:
            # Keep the usage layer, including players it observed in match sheets, until usage is rebuilt.
            observed = [row for row in previous["players"] if row["status"] == "observed"]
            data = {**data, "players": data["players"] + observed,
                    **{key: previous[key] for key in ("usage", "usage_generated_at") if key in previous}}
        if not path.exists() or json.loads(path.read_text()) != data:
            write_json(path, data)


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
    parser.add_argument("--download-players", action="store_true", help="Download and verify the pinned CSV before building")
    parser.add_argument("--source-url", help="Provenance URL when using a different EA CSV")
    parser.add_argument("--competition", nargs="+", choices=COMPETITIONS, default=list(COMPETITIONS))
    parser.add_argument("--formation", choices=FORMATIONS, default="4-3-3")
    parser.add_argument("--site-data", type=Path, default=ROOT / "site/data")
    parser.add_argument("--overrides", type=Path, default=ROOT / "data/players/identity_overrides.json")
    parser.add_argument("--roster-cache", type=Path, default=ROOT / ".cache/players/rosters")
    parser.add_argument("--roster-archive", type=Path, default=ROOT / "data/players/rosters")
    parser.add_argument("--baselines", type=Path, default=ROOT / "data/players/baselines")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--roster-date", default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--out", type=Path, default=ROOT / "out/squads")
    args = parser.parse_args(argv)
    if args.roster_date != datetime.now(timezone.utc).date().isoformat() and not args.offline:
        parser.error("An older --roster-date requires --offline; current squads cannot reconstruct past squads.")
    if args.download_players:
        with urlopen(EA_SOURCE, timeout=90) as response:
            content = response.read()
        if hashlib.sha256(content).hexdigest() != (ROOT / "data/players/ea.sha256").read_text().strip():
            raise ValueError("Downloaded EA CSV sha256 mismatch; keeping previous squad files.")
        args.players.parent.mkdir(parents=True, exist_ok=True)
        args.players.write_bytes(content)
    if args.publish and sha256(args.players) != (ROOT / "data/players/ea.sha256").read_text().strip():
        raise ValueError("EA CSV sha256 mismatch; keeping previous squad files.")
    records, metadata = load_players(args.players)
    overrides = json.loads(args.overrides.read_text())
    load_dotenv(ROOT / ".env")
    teams, sources, observed_at = {}, {}, {}
    for code in dict.fromkeys(args.competition):
        published = json.loads((args.site_data / f"{COMPETITIONS[code]}.json").read_text())
        source = rosters(code, args.roster_cache, args.roster_date, args.offline, args.roster_archive)
        payload = source["payload"]
        if payload["competition"]["code"] != code or payload["season"]["startDate"][:4] != published["season"][:4]:
            raise ValueError(f"{code}: roster competition/season differs from the published competition.")
        supported = {team["id"]: team for team in published["teams"]}
        found = {team["id"]: team for team in payload["teams"] if team["id"] in supported}
        if found.keys() != supported.keys() or (not args.publish and any(not team["squad"] for team in found.values())):
            raise ValueError(f"{code}: missing supported clubs or empty squads; refusing a partial roster.")
        for tid, team in found.items():
            if not isinstance(team.get("squad"), list):
                raise ValueError(f"{code}: invalid squad for team {tid}.")
            observed = datetime.fromisoformat(source["fetched_at"])
            if (tid in teams and teams[tid]["squad"] != team["squad"]
                    and (not args.publish or observed_at[tid] == observed)):
                raise ValueError(f"Conflicting squad snapshots for team {tid}.")
            if tid not in teams or observed > observed_at[tid]:
                teams[tid], observed_at[tid] = team, observed
        sources[code] = (published, source, supported)
    source_url = args.source_url or (EA_SOURCE if args.publish or args.download_players or
                                     args.players == parser.get_default("players") else None)
    dataset = {"file": args.players.name, "sha256": sha256(args.players), "rows": len(records),
               "url": source_url, **metadata}
    index = player_index(records)
    conflicts = set()
    if args.publish:
        counts = Counter(row["id"] for team in teams.values() for row in team["squad"])
        conflicts = {pid for pid, count in counts.items() if count > 1}
        for team in teams.values():
            ids = [row["id"] for row in team["squad"]]
            if len(ids) != len(set(ids)):
                raise ValueError(f"Repeated player ID within squad {team['id']}.")
    clean = [{**team, "squad": [row for row in team["squad"] if row["id"] not in conflicts]}
             for team in teams.values()]
    clubs = {club["id"]: club for club in match_squads(clean, index, overrides)}
    for tid, team in teams.items():
        for row in team["squad"]:
            if row["id"] in conflicts:
                print(f"WARNING: {team['name']}: ambiguous club membership for {row['name']} ({row['id']}).")
                player = match_player(row, {})
                player.update(status="ambiguous", reason="provider_id_in_multiple_clubs")
                clubs[tid]["players"].append(player)
    for club in clubs.values():
        club["best_xi"] = select_xi(club["players"], args.formation)
        club["coverage"] = dict(Counter(row["status"] for row in club["players"]))
        club["coverage"].setdefault("matched", 0)
    if args.publish:
        publish_clubs(clubs, sources, dataset, args)
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
