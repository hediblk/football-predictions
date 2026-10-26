import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from forecast_calibration.backtest_feasibility import ARTIFACT, PICKS, digest, select_bets, stake_bets, summarize
from forecast_calibration.backtest_replay import _load_content, replay_season
from forecast_calibration.dataset import feature_code_hash
from standing_prediction.odds import FOOTBALL_DATA_UK_BASE, _football_data_uk_season_code
from standing_prediction.utils import normalize_team

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_site_data import validate_payload

LEAGUES = {"E0": "premier-league", "SP1": "la-liga", "D1": "bundesliga", "I1": "serie-a", "F1": "ligue-1"}
COMP = {"E0": "PL", "SP1": "PD", "D1": "BL1", "I1": "SA", "F1": "FL1"}
BOOKS = {"avg": ("Avg", "BbAv"), "max": ("Max", "BbMx"), "bet365": ("B365",),
         "pinnacle": ("PS", "P"), "betfair": ("BF",), "betfair_exchange": ("BFE",),
         "betfred": ("BFD",), "betvictor": ("BV", "VC"), "bwin": ("BW",),
         "paddypower": ("PP",), "skybet": ("SKB", "SK"), "williamhill": ("WH",),
         "ladbrokes": ("LB",), "interwetten": ("IW",), "1xbet": ("1XB",), "betmgm": ("BMGM",)}


def quote(row, prefixes, timing):
    for prefix in prefixes:
        names = [f"{prefix}{'C' if timing == 'close' else ''}{side}" for side in "HDA"]
        values = pd.to_numeric(pd.Series([row.get(name) for name in names]), errors="coerce").to_numpy(float)
        if np.isfinite(values).all() and (values > 1).all():
            return values.tolist()
    return None


def valid_pair(values):
    return [float(value) for value in values] if all(pd.notna(value) and np.isfinite(value) and value >= 0 for value in values) else None


def stakes_tag(receipt):
    evidence = receipt.get("stakes")
    if evidence is None:
        return None
    for team in evidence["teams"]:
        for metric, threshold in (("title", 8), ("ucl", 15), ("releg", 15)):
            values = [value for value in team.get(metric, []) if value is not None]
            if values and max(values) - min(values) >= threshold:
                return True
    return False


def identities(site_data, cache_dir):
    clubs, fixtures, receipts, inputs = {}, {}, {}, {}

    def club(name, number):
        key = normalize_team(name) if name else ""
        if key and isinstance(number, int) and number > 0:
            clubs.setdefault(key, set()).add(number)

    def identity_key(name, number):
        key = normalize_team(name)
        if key:
            return key
        aliases = sorted(key for key, numbers in clubs.items() if number in numbers)
        return aliases[0] if len(aliases) == 1 else f"provider:{number}"

    for path in sorted((cache_dir / "football-data").glob("*.json")):
        try:
            wrapped = json.loads(path.read_text())
            data = json.loads(wrapped["content"])
            for match in data.get("matches", []):
                for side in ("homeTeam", "awayTeam"):
                    team = match.get(side) or {}
                    club(team.get("name"), team.get("id"))
            for team in data.get("teams", []):
                club(team.get("name"), team.get("id"))
        except (OSError, ValueError, TypeError, KeyError):
            continue
    for league, slug in LEAGUES.items():
        path = site_data / "matches" / f"{slug}.json"
        if not path.exists():
            continue
        inputs[f"site-data/{path.relative_to(site_data)}"] = digest(path)
        matches = json.loads(path.read_text())["matches"]
        for match in matches:
            for side in ("home", "away"):
                club(match[side], match[f"{side}_id"])
            key = (COMP[league], pd.Timestamp(match["kickoff"]).date().isoformat(),
                   identity_key(match["home"], match["home_id"]), identity_key(match["away"], match["away_id"]))
            fixtures[key] = match
        for path in sorted((site_data / "history").glob(f"*/forecasts/{slug}.json")):
            inputs[f"site-data/{path.relative_to(site_data)}"] = digest(path)
            for fixture, receipt in json.loads(path.read_text())["fixtures"].items():
                receipts[(COMP[league], int(fixture))] = receipt
    return {name: next(iter(ids)) for name, ids in clubs.items() if len(ids) == 1}, fixtures, receipts, inputs


def enrich(frame, raw, clubs, fixtures, receipts):
    raw = raw.copy()
    raw["home_key"] = raw.HomeTeam.map(normalize_team)
    raw["away_key"] = raw.AwayTeam.map(normalize_team)
    if raw.duplicated(["home_key", "away_key"]).any():
        raise ValueError("Duplicate source fixture identities")
    sources = raw.set_index(["home_key", "away_key"]).to_dict("index")
    rows, missing, receipt_exclusions = [], [], 0
    for match in frame.to_dict("records"):
        home, away = match["homeTeam"], match["awayTeam"]
        source = sources.get((home, away))
        if source is None:
            missing.append([home, away])
            continue
        kickoff = pd.to_datetime(match["utcDate"], utc=True)
        key = (COMP[match["league"]], kickoff.date().isoformat(), home, away)
        fixture = fixtures.get(key)
        score = [int(match["homeGoals"]), int(match["awayGoals"])]
        if fixture and fixture.get("score") != score:
            fixture = None
        prices = {book: {timing: quote(source, prefixes, timing) for timing in ("pre", "close")}
                  for book, prefixes in BOOKS.items()
                  if any(f"{prefix}H" in raw or f"{prefix}CH" in raw for prefix in prefixes)}
        row = {"id": fixture["id"] if fixture else None, "comp": COMP[match["league"]],
               "kickoff": kickoff.isoformat(), "home": source["HomeTeam"], "away": source["AwayTeam"],
               "home_key": home, "away_key": away, "home_id": clubs.get(home), "away_id": clubs.get(away),
               "matchday": fixture.get("md") if fixture else None, "forecast": "replayed",
               "at": pd.to_datetime(match["forecast_at"], utc=True).isoformat(), "score": score,
               "xg": valid_pair([match["home_xg"], match["away_xg"]]),
               "p": [float(match[f"p_{side}"]) for side in "hda"],
               "elo": [float(match[f"elo_{side}"]) for side in "hda"],
               "exp": valid_pair([match["exp_home"], match["exp_away"]]),
               "stakes": None, "rating_gap": None, "prices": prices}
        rows.append(row)
        receipt = receipts.get((row["comp"], row["id"]))
        if receipt:
            if pd.Timestamp(receipt["kickoff"]) != kickoff or pd.Timestamp(receipt["generated_at"]) >= kickoff:
                receipt_exclusions += 1
                continue
            published = {**row, "forecast": "published", "at": receipt["generated_at"],
                         "p": receipt["p"], "elo": receipt.get("elo"), "exp": receipt.get("exp"),
                         "stakes": stakes_tag(receipt),
                         "prices": {book: {"pre": None, "close": values["close"]} for book, values in prices.items()}}
            rows.append(published)
    if missing:
        raise ValueError(f"Unmatched source fixtures: {missing[:5]} ({len(missing)} total)")
    return rows, receipt_exclusions


def add_published(rows, season, clubs, fixtures, receipts):
    seen = {(row["comp"], row["id"]) for row in rows if row["id"] is not None}
    excluded = 0
    for (comp, day, home, away), fixture in fixtures.items():
        kickoff = pd.Timestamp(fixture["kickoff"])
        fixture_season = kickoff.year - (kickoff.month < 7)
        receipt = receipts.get((comp, fixture["id"]))
        if fixture_season != season or fixture.get("status") != "FINISHED" or not receipt or (comp, fixture["id"]) in seen:
            continue
        if pd.Timestamp(receipt["kickoff"]) != kickoff or pd.Timestamp(receipt["generated_at"]) >= kickoff:
            excluded += 1
            continue
        rows.append({"id": fixture["id"], "comp": comp, "kickoff": kickoff.isoformat(),
                     "home": fixture["home"], "away": fixture["away"], "home_key": home, "away_key": away,
                     "home_id": fixture["home_id"], "away_id": fixture["away_id"], "matchday": fixture.get("md"),
                     "forecast": "published", "at": receipt["generated_at"], "score": fixture["score"],
                     "xg": fixture.get("xg"), "p": receipt["p"], "elo": receipt.get("elo"),
                     "exp": receipt.get("exp"), "stakes": stakes_tag(receipt), "rating_gap": None,
                     "prices": {book: {"pre": None, "close": None} for book in BOOKS}})
    return excluded


def coverage(rows):
    result = {"rows": len(rows), "replayed": 0, "published": 0, "by_comp": {}, "prices": {}}
    fields = {"missing_ids": lambda row: row["id"] is None or row["home_id"] is None or row["away_id"] is None,
              "missing_xg": lambda row: row["xg"] is None, "missing_exp": lambda row: row["exp"] is None,
              "missing_stakes": lambda row: row["stakes"] is None, "missing_matchday": lambda row: row["matchday"] is None,
              "missing_rating": lambda row: row["rating_gap"] is None}
    for row in rows:
        kind = row["forecast"]
        result[kind] += 1
        comp = result["by_comp"].setdefault(row["comp"], {"replayed": 0, "published": 0, **{field: 0 for field in fields}})
        comp[kind] += 1
        for field, missing in fields.items():
            comp[field] += int(missing(row))
        for book, quotes in row["prices"].items():
            counts = result["prices"].setdefault(book, {"pre": 0, "close": 0})
            for timing in ("pre", "close"):
                counts[timing] += int(quotes[timing] is not None)
    return result


def parity(rows, season, bootstrap):
    frame = []
    reverse = {comp: league for league, comp in COMP.items()}
    for row in rows:
        if row["forecast"] != "replayed":
            continue
        probabilities = np.array(row["p"]) / sum(row["p"])
        score = row["score"]
        record = {"league": reverse[row["comp"]], "season": season, "homeTeam": row["home_key"],
                  "awayTeam": row["away_key"], "utcDate": row["kickoff"], "forecast_at": row["at"],
                  "day": row["kickoff"][:10], "y": 0 if score[0] > score[1] else 1 if score[0] == score[1] else 2,
                  **{f"p_{side}": value for side, value in zip("hda", probabilities)}}
        for timing in ("pre", "close"):
            prices = row["prices"].get("avg", {}).get(timing) or [np.nan] * 3
            record.update({f"average_{timing}_{side}": value for side, value in zip("hda", prices)})
        frame.append(record)
    frame = pd.DataFrame(frame).sort_values(["utcDate", "league", "homeTeam"]).reset_index(drop=True)
    results = []
    for pick in PICKS:
        for method in ("flat", "quarter_kelly"):
            strategy = {"v": 1, "universe": {"comps": [], "seasons": [season], "include": [], "exclude": [],
                         "venue": "any", "forecast": "replayed"}, "market": "1x2",
                        "rule": {"pick": "edge" if pick.startswith("edge_") else pick,
                                 "conditions": [{"field": "edge", "op": ">=", "value": int(pick.split("_")[1]) / 100}]
                                 if pick.startswith("edge_") else []},
                        "stake": {"method": "kelly" if method == "quarter_kelly" else "flat", "fraction": 0.25,
                                  "cap": 0.03, "unit": 1, "daily_cap": 1, "trust": 1, "base": "start_of_day"},
                        "execution": {"book": "avg", "timing": "pre", "commission": 0}, "bankroll": 100}
            result = summarize(stake_bets(select_bets(frame, pick=pick), method), bootstrap=bootstrap)
            results.append({"strategy": strategy, "options": {"bootstrap": bootstrap, "seed": 7}, "summary": result})
    return results


def write_season(path, payload):
    if path.exists():
        previous = json.loads(path.read_text())
        if {k: v for k, v in previous.items() if k != "generated_at"} == {k: v for k, v in payload.items() if k != "generated_at"}:
            return False
    validate_payload(payload, "backtest")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
    temporary.replace(path)
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build domestic 1X2 backtest season files; historical prices stay local pending D1")
    parser.add_argument("--dataset", type=Path, default=ROOT / "out/global-calibration/features/dataset.csv")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / ".cache")
    parser.add_argument("--work-dir", type=Path, default=ROOT / "out/backtest-build")
    parser.add_argument("--site-data", type=Path, default=ROOT / "site/data")
    parser.add_argument("--dest", type=Path)
    parser.add_argument("--seasons", type=int, nargs="+")
    parser.add_argument("--current-only", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--publish", action="store_true", help="Publish prices to the candidate site; requires D1 authorization")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild frozen past-season files even when calibration is unchanged")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--bootstrap", type=int, default=2000)
    args = parser.parse_args(argv)
    if args.workers < 1 or args.bootstrap < 1:
        parser.error("workers and bootstrap must be positive")
    artifact = json.loads(ARTIFACT.read_text())
    current = datetime.now(timezone.utc).year - (datetime.now(timezone.utc).month < 7)
    seasons = sorted(set(args.seasons or ([current] if args.current_only else [*artifact["dataset"]["seasons"], current])))
    destination = (args.dest or (args.site_data / "backtest" if args.publish else ROOT / "out/backtest")).resolve()
    if not args.publish and ROOT / "out" not in destination.parents:
        parser.error("Historical price outputs must remain under out/ until D1 permits publication")
    pending = []
    for season in seasons:
        path = destination / f"{season}.json"
        if season < current and path.exists() and not args.rebuild:
            previous = json.loads(path.read_text())
            if previous.get("provenance", {}).get("calibration_sha256") == digest(ARTIFACT):
                validate_payload(previous, "backtest")
                print(f"Retained frozen {path}", flush=True)
                continue
        pending.append(season)
    seasons = pending
    if not seasons:
        return
    features = None
    if any(season in artifact["dataset"]["seasons"] for season in seasons):
        if digest(args.dataset) != artifact["dataset"]["sha256"]:
            raise ValueError("Dataset differs from the saved calibration artifact")
        features = pd.read_csv(args.dataset)
    if not set(seasons) <= set(artifact["dataset"]["seasons"] + [current]):
        parser.error("Only calibration seasons and the current independent season are supported")
    clubs, fixtures, receipts, identity_hashes = identities(args.site_data, args.cache_dir)
    parts = {}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs = {pool.submit(replay_season, league, season, args.cache_dir, args.work_dir,
                            features[(features.league == league) & (features.season == season)]
                            if features is not None and season in artifact["dataset"]["seasons"] else None,
                            args.offline): (league, season) for season in seasons for league in LEAGUES}
        for future in as_completed(jobs):
            league, season = jobs[future]
            parts[(league, season)] = future.result()
            print(f"Replayed {league}/{season}: {len(parts[(league, season)])} matches", flush=True)
    for season in seasons:
        rows, inputs, excluded = [], {}, 0
        for league in LEAGUES:
            url = f"{FOOTBALL_DATA_UK_BASE}/{_football_data_uk_season_code(season)}/{league}.csv"
            content = _load_content(args.cache_dir, url, args.offline)
            inputs[url] = hashlib.sha256(content.encode()).hexdigest()
            raw = pd.read_csv(io.StringIO(content))
            enriched, missing = enrich(parts[(league, season)], raw, clubs, fixtures, receipts)
            rows.extend(enriched)
            excluded += missing
            stamp = args.work_dir / "parts" / f"{league}_{season}.json"
            inputs[str(stamp)] = digest(stamp)
            metadata = json.loads(stamp.read_text())
            inputs.update(metadata.get("signature", metadata)["inputs"])
        excluded += add_published(rows, season, clubs, fixtures, receipts)
        rows.sort(key=lambda row: (row["kickoff"], row["comp"], row["home_key"], row["forecast"]))
        if not rows:
            raise ValueError(f"No covered matches for {season}")
        payload = {"version": 1, "season": season, "generated_at": datetime.now(timezone.utc).isoformat(),
                   "calibration_version": artifact["version"],
                   "columns": {key: [row[key] for row in rows] for key in rows[0]}, "coverage": coverage(rows),
                   "provenance": {"input_sha256": {**inputs, **identity_hashes}, "calibration_sha256": digest(ARTIFACT),
                                  "model_code_sha256": feature_code_hash(), "exporter_sha256": digest(__file__),
                                  "dataset_sha256": artifact["dataset"]["sha256"] if season in artifact["dataset"]["seasons"] else None,
                                  "receipt_exclusions": excluded,
                                  "display_identity_sha256": hashlib.sha256(json.dumps(clubs, sort_keys=True).encode()).hexdigest(),
                                  "forecast_label": "replayed, in-sample for calibration" if season in artifact["dataset"]["seasons"]
                                  else "current season, unseen by calibration; later strategy choices may use these results",
                                  "timing": "Tuesday/Friday 00:00 UTC origins, later pre-closing/closing collection approximated; old kickoffs anchored at noon UTC",
                                  "availability": {"stakes": "published receipts only", "rating_gap": "unavailable",
                                                   "provider_ids": "retrospective display/link enrichment"},
                                  "results_cutoff_by_comp": {COMP[league]: pd.to_datetime(parts[(league, season)].utcDate, utc=True).max().isoformat()
                                                             for league in LEAGUES},
                                  "offline": args.offline,
                                  "publication": "D1 explicitly authorized" if args.publish else "local_pending_D1"},
                   "parity": parity(rows, season, args.bootstrap)}
        changed = write_season(destination / f"{season}.json", payload)
        print(f"{'Wrote' if changed else 'Retained unchanged'} {destination / f'{season}.json'} ({len(rows)} forecast rows)", flush=True)


if __name__ == "__main__":
    main()
