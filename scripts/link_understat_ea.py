import argparse
from collections import defaultdict
from functools import lru_cache
from html import unescape
import json
from pathlib import Path
import random

import pandas as pd

from build_ea_vintages import ROOT, sha256, write_if_changed
from standing_prediction.squads import name_score, name_tokens
from standing_prediction.utils import normalize_team


@lru_cache(maxsize=None)
def club_key(name):
    aliases = {"Chievo Verona": "Chievo", "ChievoVerona": "Chievo", "Piemonte Calcio": "Juventus",
               "Latium": "Lazio", "Bergamo Calcio": "Atalanta", "Roma FC": "Roma",
               "Milano FC": "Milan", "Lombardia FC": "Inter", "Napoli FC": "Napoli"}
    return normalize_team(aliases.get(name, name))


@lru_cache(maxsize=None)
def clean_name(name):
    return unescape(name).translate(str.maketrans({"'": "", "’": "", "ð": "d", "Ð": "D",
                                                   "þ": "th", "Þ": "Th", "æ": "ae", "Æ": "Ae",
                                                   "œ": "oe", "Œ": "Oe", "ß": "ss"}))


def score_name(name, aliases):
    name = clean_name(name)
    aliases = [clean_name(alias) for alias in aliases]
    score = name_score(name, aliases, appearance=True)
    if score is not None:
        return score
    parts = name.split(maxsplit=1)
    if len(parts) == 2:
        first, surname = name_tokens(parts[0]), name_tokens(parts[1])
        for alias in aliases:
            other = alias.split(maxsplit=1)
            if len(other) == 2 and surname and surname == name_tokens(other[1]):
                initial = name_tokens(other[0])
                if len(initial) == len(first) == 1 and len(next(iter(initial))) == 1:
                    if next(iter(first)).startswith(next(iter(initial))):
                        return 4
    return None


def load_ratings(manifest, cache):
    pools, people, earliest = defaultdict(dict), {}, {}
    for vintage in manifest["vintages"]:
        path = cache / vintage["file"]
        if sha256(path) != vintage["sha256"]:
            raise ValueError(f"Vintage hash mismatch: {path}")
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        if len(frame) != vintage["rows"] or frame.ea_id.duplicated().any():
            raise ValueError(f"Vintage count/identity mismatch: {path}")
        season = vintage["season"]
        for row in frame.itertuples(index=False):
            ea_id = int(row.ea_id)
            if not 1 <= int(row.overall) <= 99:
                raise ValueError(f"Invalid rating in {path}: {ea_id}")
            person = people.setdefault(ea_id, {"dobs": set()})
            if row.dob:
                person["dobs"].add(row.dob)
            key = (season, ea_id)
            earliest[key] = min(earliest.get(key, vintage["available_from"]), vintage["available_from"])
            pool = pools[(season, club_key(row.club))]
            candidate = pool.setdefault(ea_id, {"names": set(), "evidence": []})
            candidate["names"].update((row.name, row.short_name))
            # Keep one example of each name/club/DOB combination, rather than every weekly repeat.
            evidence = (row.name, row.short_name, row.club, row.dob)
            if evidence not in candidate.get("seen", set()):
                candidate.setdefault("seen", set()).add(evidence)
                candidate["evidence"].append((vintage["id"], *evidence))
    return pools, people, earliest


def load_appearances(directory):
    frames, sources = [], []
    for path in sorted(directory.glob("*/*.csv.gz")):
        frame = pd.read_csv(path, usecols=["player_id", "name", "team", "date", "minutes"],
                            dtype={"player_id": int, "name": str, "team": str})
        frame["season"] = int(path.name.split(".")[0])
        frame["league"] = path.parent.name
        frames.append(frame)
        sources.append({"file": path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path),
                        "rows": len(frame), "sha256": sha256(path)})
    if len(frames) != 60:
        raise ValueError(f"Expected 60 league-seasons, got {len(frames)}")
    return pd.concat(frames, ignore_index=True), sources


def link(appearances, pools, people):
    links, career = [], defaultdict(set)
    for (league, season, team, player_id), group in appearances.groupby(["league", "season", "team", "player_id"]):
        names = sorted(set(group.name))
        pool = pools.get((season, club_key(team)), {})
        scores = {}
        for ea_id, candidate in pool.items():
            values = [score_name(name, candidate["names"]) for name in names]
            values = [score for score in values if score is not None]
            if values:
                scores[ea_id] = min(values)
        best = min(scores.values(), default=None)
        candidates = sorted(ea_id for ea_id, score in scores.items() if score == best)
        if len(candidates) == 1:
            career[player_id].add(candidates[0])
        links.append({"league": league, "season": season, "team": team, "understat_id": player_id,
                      "understat_names": " | ".join(names), "minutes": round(group.minutes.sum(), 4),
                      "status": "unmatched", "ea_id": "", "method": "", "confidence": "",
                      "ea_name": "", "ea_dob": "", "ea_club": "", "evidence_vintage": "",
                      "candidate_ea_ids": " | ".join(map(str, candidates)), "reason": "no_club_name_match",
                      "score": best, "candidates": candidates})
    reverse = defaultdict(set)
    for player_id, candidates in career.items():
        if len(candidates) == 1:
            reverse[next(iter(candidates))].add(player_id)
    anchors = {}
    for row in links:
        ids = career[row["understat_id"]]
        if len(ids) == 1 and len(row["candidates"]) == 1:
            anchors.setdefault(row["understat_id"], row)
    for row in links:
        ids = career[row["understat_id"]]
        if len(ids) > 1:
            row.update(status="ambiguous", reason="career_ea_id_conflict", candidate_ea_ids=" | ".join(map(str, sorted(ids))))
            continue
        if not ids:
            if row["candidates"]:
                row.update(status="ambiguous", reason="multiple_club_name_matches")
            continue
        ea_id = next(iter(ids))
        if len(reverse[ea_id]) > 1:
            row.update(status="ambiguous", reason="ea_id_linked_to_multiple_understat_ids")
            continue
        if len(people[ea_id]["dobs"]) > 1:
            row.update(status="ambiguous", reason="ea_birth_date_conflict")
            continue
        if row["candidates"] and ea_id not in row["candidates"]:
            row.update(status="ambiguous", reason="career_disagrees_with_club_candidates")
            continue
        local = ea_id in row["candidates"]
        anchor = row if local else anchors[row["understat_id"]]
        candidate = pools[(anchor["season"], club_key(anchor["team"]))][ea_id]
        evidence = min(candidate["evidence"], key=lambda item: (
            min((score_name(name, item[1:3]) for name in anchor["understat_names"].split(" | ")
                 if score_name(name, item[1:3]) is not None), default=99), item[0]))
        methods = {0: "exact_name_club", 1: "name_tokens_club", 2: "name_tokens_club",
                   3: "single_name_club", 4: "initial_surname_club"}
        method = methods[row["score"]] if local and len(row["candidates"]) == 1 else "career_consistency"
        row.update(status="matched", ea_id=ea_id, method=method,
                   confidence="high" if method == "exact_name_club" else "medium",
                   ea_name=evidence[1], ea_dob=evidence[4],
                   ea_club=evidence[3], evidence_vintage=evidence[0], reason="")
    for row in links:
        del row["score"], row["candidates"]
    return pd.DataFrame(links)


def report(links, appearances, earliest, report_dir, provenance):
    keys = ["league", "season", "team", "player_id"]
    joined = appearances.merge(links.rename(columns={"understat_id": "player_id"})[
        keys + ["status", "ea_id"]], on=keys, validate="many_to_one")
    joined["identity_minutes"] = joined.minutes.where(joined.status.eq("matched"), 0)
    available = [earliest.get((season, int(ea_id))) if status == "matched" else None
                 for season, ea_id, status in zip(joined.season, joined.ea_id, joined.status)]
    # Parse timestamps, rather than compare date strings with differing fractional precision.
    eligible = pd.to_datetime(available, utc=True, format="mixed") < pd.to_datetime(joined.date, utc=True)
    joined["rated_minutes"] = joined.minutes.where(eligible, 0)
    coverage = joined.groupby(["league", "season"])[["minutes", "identity_minutes", "rated_minutes"]].sum()
    coverage["identity_pct"] = 100 * coverage.identity_minutes / coverage.minutes
    coverage["rated_pct"] = 100 * coverage.rated_minutes / coverage.minutes
    coverage = coverage.reset_index()
    write_if_changed(report_dir / "coverage.csv", coverage.to_csv(index=False, float_format="%.4f").encode())
    matched = links[links.status.eq("matched")].sort_values(["league", "season", "team", "understat_id"])
    sample = matched.iloc[random.Random(20261016).sample(range(len(matched)), 30)]
    write_if_changed(report_dir / "spot_checks.csv", sample.to_csv(index=False).encode())
    lines = ["## Minutes coverage", "", "Denominator: all archived appearance minutes, separately per league-season.",
             "Identity coverage includes retrospective career confirmation. Rated coverage additionally requires an EA",
             "record in that season's edition available strictly before kickoff; no future or previous-edition fallback.",
             "Date-only snapshots become available at the next UTC midnight. Excluded Understat matches are outside the denominator.",
             "", "| League | Season | Minutes | Identity % | Dated rating % |", "| --- | --- | ---: | ---: | ---: |"]
    for row in coverage.itertuples(index=False):
        lines.append(f"| {row.league} | {row.season}/{str(row.season + 1)[2:]} | {row.minutes:,.0f} | {row.identity_pct:.2f} | {row.rated_pct:.2f} |")
    lines += ["", "## 30 random link checks", "", "Seed 20261016; uniform sample without replacement from sorted matched club-season rows.",
              "Each row below is checked against the named, hash-verified vintage's EA record and its career mapping.",
              "Birth dates are EA evidence only: Understat has no birth dates. Confidence is qualitative.",
              "", "| Understat ID / name | Season / Understat club | EA ID / name | EA club / birth date | Method / confidence | Vintage |",
              "| --- | --- | --- | --- | --- | --- |"]
    for row in sample.itertuples(index=False):
        lines.append(f"| {row.understat_id} / {row.understat_names} | {row.season} / {row.team} | {row.ea_id} / {row.ea_name} | {row.ea_club} / {row.ea_dob or 'missing'} | {row.method} / {row.confidence} | {row.evidence_vintage} |")
    lines += ["", "## Unresolved links", "", "| Reason | Club-season players |", "| --- | ---: |"]
    for reason, count in links[links.status.ne("matched")].reason.value_counts().items():
        lines.append(f"| {reason} | {count} |")
    write_if_changed(report_dir / "review.md", ("\n".join(lines) + "\n").encode())
    write_if_changed(report_dir / "inputs.json", (json.dumps(provenance, indent=2) + "\n").encode())
    totals = coverage[["minutes", "identity_minutes", "rated_minutes"]].sum()
    print(f"{len(links):,} club-season players; {len(matched):,} linked; "
          f"minutes: identity {100 * totals.identity_minutes / totals.minutes:.2f}%, "
          f"dated rating {100 * totals.rated_minutes / totals.minutes:.2f}%")
    print(links[links.status.ne("matched")].reason.value_counts().to_string())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=ROOT / ".cache/players")
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/players/ea/vintages.json")
    parser.add_argument("--understat", type=Path, default=ROOT / "data/players/understat")
    parser.add_argument("--output", type=Path, default=ROOT / "data/players/understat_ea_links.csv")
    parser.add_argument("--report-dir", type=Path, default=ROOT / "out/ea-links")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    pools, people, earliest = load_ratings(manifest, args.cache)
    appearances, sources = load_appearances(args.understat)
    links = link(appearances, pools, people)
    write_if_changed(args.output, links.to_csv(index=False, lineterminator="\n").encode())
    report(links, appearances, earliest, args.report_dir,
           {"manifest_sha256": sha256(args.manifest), "understat": sources, "links_sha256": sha256(args.output)})
