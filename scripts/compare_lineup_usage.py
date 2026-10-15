import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path

from standing_prediction.lineup_usage import compare_usage
from build_squads import COMPETITIONS, ROOT, sha256, write_json


def comparisons(baseline, data_dir, retrospective=False):
    slug = COMPETITIONS[baseline["competition"]]
    competition = json.loads((data_dir / f"{slug}.json").read_text())
    if competition["season"] != baseline["season"]:
        raise ValueError("Match data and ideal-XI baseline belong to different seasons.")
    matches = json.loads((data_dir / "matches" / f"{slug}.json").read_text())
    clubs = {club["id"]: club for club in baseline["clubs"]}
    rows, excluded = [], 0
    for fixture in sorted(matches["matches"], key=lambda row: (row["kickoff"], row["id"])):
        if fixture["status"] != "FINISHED":
            continue
        earlier = datetime.fromisoformat(fixture["kickoff"]) <= datetime.fromisoformat(baseline["created_at"])
        if earlier and not retrospective:
            excluded += 1
            continue
        path = data_dir / "match" / baseline["season"][:4] / slug / f"{fixture['id']}.json"
        detail = json.loads(path.read_text()) if path.exists() else {}
        if detail and (detail["id"] != fixture["id"] or detail["competition"] != slug or
                       detail["kickoff"] != fixture["kickoff"]):
            raise ValueError(f"Match detail identity differs from fixture {fixture['id']}.")
        for side, key, opponent in (("h", "home_id", "away"), ("a", "away_id", "home")):
            club = clubs.get(fixture[key])
            if club is None:
                raise ValueError(f"Fixture {fixture['id']} includes a club absent from the baseline.")
            rows.append({"fixture_id": fixture["id"], "kickoff": fixture["kickoff"], "club_id": club["id"],
                         "club": club["name"], "opponent": fixture[opponent], "side": side,
                         "mode": "retrospective" if earlier else "prospective", "baseline_id": baseline["baseline_id"],
                         "detail_sha256": sha256(path) if detail else None, **compare_usage(club, detail, side)})
    return rows, excluded


def report(data):
    lines = [f"# {data['name']} ideal XI usage", "",
             f"Baseline {data['baseline_id']}, frozen {data['baseline_created_at']}.", "",
             "Started and substitute come from Understat's match sheet; minutes are reported by Understat. "
             "Exact entry times are not inferred from minutes or joined from another provider. "
             "Did not play is assigned only when every appearance in that side's sheet maps to the baseline squad. "
             "Otherwise an unobserved XI player is unknown. Unused bench versus absent is unavailable.", "",
             "Ideal minutes share is the unweighted sum of those eleven players' minutes (each capped at 90), "
             "divided by 990. It is omitted if any selected player's participation is unknown or a slot is unfilled. "
             "It does not measure causal strength loss.", ""]
    if data["retrospective"]:
        lines.extend(["Retrospective diagnostics use today's squad and XI for older games. They are not pre-match "
                      "baselines and cannot be used as historical forecast inputs.", ""])
    lines.extend([f"Club-game observations: {len(data['matches'])}. Finished fixtures excluded before the baseline: "
                  f"{data['excluded_earlier_fixtures']}.", ""])
    if not data["matches"]:
        lines.append("Waiting for finished matches after the baseline was frozen. Rerun this command after match data refreshes.")
    else:
        lines.extend(["| Date | Club | Opponent | Mode | Started | Sub | Did not play | Unknown | Ideal minutes |",
                      "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |"])
        for row in data["matches"]:
            counts = row.get("counts", {})
            share = row.get("ideal_minutes_share")
            lines.append(f"| {row['kickoff'][:10]} | {row['club']} | {row['opponent']} | {row['mode']} | "
                         f"{counts.get('started', 0)} | {counts.get('substitute', 0)} | {counts.get('did_not_play', 0)} | "
                         f"{counts.get('unknown', 0)} | {str(share) + '%' if share is not None else row['status']} |")
        latest = {row["club_id"]: row for row in data["matches"] if row["players"]}
        for row in latest.values():
            lines.extend(["", f"## {row['club']} v {row['opponent']} · {row['kickoff'][:10]}", "",
                          f"{row['mode']} · {row['status']}", "",
                          "| Role | Player | Participation | Minutes |", "| --- | --- | --- | ---: |"])
            for player in row["players"]:
                minutes = player["minutes"]
                lines.append(f"| {player['role']} | {player['name']} | {player['status']} | "
                             f"{minutes if minutes is not None else '—'} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare a frozen ideal XI with collected match appearances.")
    parser.add_argument("--baseline", type=Path, default=ROOT / "out/squads/PD.json")
    parser.add_argument("--data", type=Path, default=ROOT / "site/data")
    parser.add_argument("--out", type=Path, default=ROOT / "out/squads")
    parser.add_argument("--retrospective", action="store_true", help="Include explicitly labelled older-game diagnostics")
    args = parser.parse_args(argv)
    baseline = json.loads(args.baseline.read_text())
    rows, excluded = comparisons(baseline, args.data, args.retrospective)
    data = {"name": baseline["name"], "baseline_id": baseline["baseline_id"],
            "baseline_created_at": baseline["created_at"], "baseline_sha256": sha256(args.baseline),
            "retrospective": args.retrospective, "excluded_earlier_fixtures": excluded, "matches": rows}
    suffix = "usage-diagnostic" if args.retrospective else "usage"
    path = args.out / f"{baseline['competition']}-{suffix}.json"
    write_json(path, data)
    path.with_suffix(".md").write_text(report(data), encoding="utf-8")
    print(f"{baseline['competition']}: {len(rows)} club-games, {dict(Counter(row['status'] for row in rows))} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
