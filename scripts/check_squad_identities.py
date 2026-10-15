import argparse
from collections import Counter
import json
from pathlib import Path

from build_squads import ROOT, sha256, write_json
from standing_prediction.lineup_usage import identify_appearance


def audit(baseline, data_dir):
    competition = json.loads((data_dir / "champions-league.json").read_text())
    if competition["season"] != baseline["season"]:
        raise ValueError("Squad and Champions League seasons differ.")
    fixtures = json.loads((data_dir / "matches/champions-league.json").read_text())["matches"]
    clubs = {club["id"]: club for club in baseline["clubs"]}
    counts, bindings, appearances, issues = Counter(), {}, [], []
    for fixture in fixtures:
        path = data_dir / "match" / baseline["season"][:4] / "champions-league" / f"{fixture['id']}.json"
        if fixture["status"] != "FINISHED" or not path.exists():
            continue
        detail = json.loads(path.read_text())
        if "heat" not in detail:
            continue
        if (detail["id"] != fixture["id"] or detail["kickoff"] != fixture["kickoff"] or
                detail["competition"] != "champions-league" or "uefa" not in detail["sources"]):
            raise ValueError(f"Heatmap fixture identity differs: {path}")
        counts["heatmap_fixtures"] += 1
        detail_hash = sha256(path)
        for side, key in (("h", "home_id"), ("a", "away_id")):
            club = clubs.get(fixture[key])
            if not club:
                continue
            counts["supported_club_games"] += 1
            physical = detail["physical"][side]["players"]
            observed = {row["id"]: row for row in physical}
            heat = {row["id"] for row in detail["heat"][side]["players"]}
            starters = {row["id"]: row for row in detail["positions"][side]}
            if (len(observed) != len(physical) or len(starters) != 11 or
                    not heat <= observed.keys() or not starters.keys() <= observed.keys()):
                issues.append({"fixture_id": fixture["id"], "club_id": club["id"], "reason": "invalid_player_sets"})
            counts["starters_without_heatmap"] += len(starters.keys() - heat)
            counts["heatmap_substitutes"] += len(heat - starters.keys())
            assigned = set()
            for row in physical:
                pid = identify_appearance(row["player"], club["players"])
                record = {"fixture_id": fixture["id"], "club_id": club["id"], "uefa_id": row["id"],
                          "name": row["player"], "player_id": pid, "starter": row["id"] in starters,
                          "heatmap": row["id"] in heat, "detail_sha256": detail_hash}
                for family, included in (("physical", True), ("heat", record["heatmap"]),
                                         ("starters", record["starter"])):
                    if included:
                        counts[family] += 1
                        counts[f"matched_{family}"] += pid is not None
                reason = None
                if pid is None:
                    reason = "unmatched_name"
                elif pid in assigned:
                    reason = "repeated_squad_identity"
                elif row["id"] in bindings and bindings[row["id"]] != pid:
                    reason = "conflicting_uefa_identity"
                elif record["starter"] and starters[row["id"]]["player"] != row["player"]:
                    reason = "inconsistent_starter_name"
                if reason:
                    issues.append({**record, "reason": reason})
                if pid is not None:
                    assigned.add(pid)
                    bindings[row["id"]] = pid
                appearances.append(record)
    return {"counts": dict(counts), "unique_mapped_players": len(set(bindings.values())),
            "issues": issues, "appearances": appearances}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Cross-check supported squad names against UEFA heatmap player records.")
    parser.add_argument("--baseline", type=Path, default=ROOT / "out/squads/PD.json")
    parser.add_argument("--data", type=Path, default=ROOT / "site/data")
    parser.add_argument("--out", type=Path, default=ROOT / "out/squads/PD-identities.json")
    args = parser.parse_args(argv)
    baseline = json.loads(args.baseline.read_text())
    result = {"baseline_id": baseline["baseline_id"], "baseline_sha256": sha256(args.baseline),
              "season": baseline["season"], **audit(baseline, args.data)}
    write_json(args.out, result)
    print(f"{result['counts']}; {len(result['issues'])} issues -> {args.out}")
    return int(bool(result["issues"]) or not result["counts"].get("supported_club_games"))


if __name__ == "__main__":
    raise SystemExit(main())
