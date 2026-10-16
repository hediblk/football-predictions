import argparse
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import time
from urllib.request import urlopen
import zipfile

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    ("fifa23", "stefanoleone992/fifa-23-complete-player-dataset", 1,
     "fifa-23-complete-player-dataset.zip", "male_players.csv", "sofifa"),
    ("fc24", "stefanoleone992/ea-sports-fc-24-complete-player-dataset", 4,
     "ea-sports-fc-24-complete-player-dataset.zip", "male_players.csv", "annual"),
    ("fc25-release", "nyagami/ea-sports-fc-25-database-ratings-and-stats", 5,
     "fc25-launch.zip", "male_players.csv", "ea25"),
    ("fc25-june", "aniss7/fifa-player-data-from-sofifa-2025-06-03", 1,
     "fifa-player-data-from-sofifa-2025-06-03.zip", "player-data-full-2025-june.csv", "june25"),
    ("fc26", "rovnez/fc-26-fifa-26-player-data", 3,
     "fc-26-fifa-26-player-data.zip", "FC26_20250921.csv", "sofifa"),
]
COLUMNS = ["ea_id", "name", "short_name", "dob", "club", "overall", "positions"]


def sha256(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_if_changed(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_bytes() != content:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(path)


def normalize(frame, schema):
    if schema in {"sofifa", "annual"}:
        if schema == "annual":
            frame = frame[frame.fifa_version.astype(float).eq(24)].copy()
        frame = frame.rename(columns={"player_id": "ea_id", "long_name": "name", "club_name": "club",
                                      "player_positions": "positions", "update_as_of": "fifa_update_date"})
    elif schema == "june25":
        frame = frame.rename(columns={"player_id": "ea_id", "full_name": "name", "name": "short_name",
                                      "club_name": "club", "overall_rating": "overall", "version": "fifa_update_date"})
        frame["fifa_version"] = "25"
        frame["fifa_update"] = "2025-06-03"
        frame["short_name"] = frame.short_name.str.removesuffix(" -")
    else:
        frame = frame.rename(columns={"Name": "name", "Team": "club", "OVR": "overall", "Position": "positions"})
        frame["ea_id"] = frame.url.str.extract(r"/(\d+)$")[0]
        frame["short_name"] = frame.name
        frame["dob"] = ""
        frame["fifa_version"] = "25"
        frame["fifa_update"] = "publication"
        frame["fifa_update_date"] = ""
    return frame


def build(cache, output, download):
    old = json.loads(output.read_text()) if output.exists() else {"sources": []}
    expected = {row["id"]: row["sha256"] for row in old["sources"]}
    sources, vintages = [], []
    staging = cache / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    for source_id, ref, version, filename, member, schema in SOURCES:
        raw = cache / "research" / filename
        url = f"https://www.kaggle.com/api/v1/datasets/download/{ref}?datasetVersionNumber={version}"
        if not raw.exists():
            if not download:
                raise FileNotFoundError(f"Download https://www.kaggle.com/datasets/{ref}/versions/{version} into {raw}")
            raw.parent.mkdir(parents=True, exist_ok=True)
            time.sleep(1)
            with urlopen(url, timeout=60) as response, raw.with_suffix(".part").open("wb") as handle:
                while chunk := response.read(1024 * 1024):
                    handle.write(chunk)
            raw.with_suffix(".part").replace(raw)
        raw_hash = sha256(raw)
        if source_id in expected and expected[source_id] != raw_hash:
            raise ValueError(f"Raw source changed: {raw}; expected {expected[source_id]}")
        sources.append({"id": source_id, "url": f"https://www.kaggle.com/datasets/{ref}",
                        "version": version, "download_url": url, "file": f"research/{filename}",
                        "member": member, "sha256": raw_hash})
        groups = {}
        with zipfile.ZipFile(raw).open(member) as handle:
            columns = {"player_id", "long_name", "short_name", "dob", "club_name", "overall", "player_positions",
                       "fifa_version", "fifa_update", "fifa_update_date", "update_as_of", "full_name", "name",
                       "overall_rating", "positions", "version", "Name", "Team", "OVR", "Position", "url"}
            for frame in pd.read_csv(handle, dtype=str, keep_default_na=False, chunksize=100_000,
                                     usecols=lambda column: column in columns):
                frame = normalize(frame, schema)
                for (edition, update, day), rows in frame.groupby(["fifa_version", "fifa_update", "fifa_update_date"]):
                    edition = int(float(edition))
                    if not 15 <= edition <= 26:
                        raise ValueError(f"Unexpected edition: {edition}")
                    key = (edition, update, day)
                    if key not in groups:
                        vintage_id = f"{source_id}-{edition}-{update}-{day or 'undated'}"
                        path = staging / f"{vintage_id}.csv"
                        path.unlink(missing_ok=True)
                        groups[key] = (vintage_id, path)
                    path = groups[key][1]
                    rows[COLUMNS].to_csv(path, mode="a", header=not path.exists(), index=False, lineterminator="\n")
        for (edition, update, day), (vintage_id, path) in sorted(groups.items()):
            if not day and schema != "ea25":
                raise ValueError(f"Missing snapshot date in {vintage_id}")
            frame = pd.read_csv(path, dtype=str, keep_default_na=False)
            for column in COLUMNS:
                frame[column] = frame[column].str.strip()
            source_rows = len(frame)
            frame = frame.drop_duplicates()
            frame["ea_id"] = pd.to_numeric(frame.ea_id, errors="raise").astype(int)
            frame["overall"] = pd.to_numeric(frame.overall, errors="raise").astype(int)
            if frame.ea_id.duplicated().any() or not frame.ea_id.gt(0).all() or not frame.overall.between(1, 99).all():
                raise ValueError(f"Invalid or duplicate player in {vintage_id}")
            for dob in frame.dob[frame.dob.ne("")]:
                date.fromisoformat(dob)
            # A date-only snapshot becomes eligible the following UTC day; never infer its release hour.
            available = ((date.fromisoformat(day) + timedelta(days=1)).isoformat() + "T00:00:00Z"
                         if day else "2024-09-26T08:14:25.953Z")
            target = cache / "ea" / "vintages" / f"{vintage_id}.csv"
            content = frame.sort_values("ea_id").to_csv(index=False, lineterminator="\n").encode()
            write_if_changed(target, content)
            vintages.append({"id": vintage_id, "source": source_id,
                             "edition": f"{'FIFA' if edition <= 23 else 'FC'} {edition}",
                             "season": 1999 + edition, "update": update, "snapshot_date": day or None,
                             "available_from": available,
                             "date_basis": "source_snapshot_date" if day else "dataset_publication_upper_bound",
                             "file": target.relative_to(cache).as_posix(), "rows": len(frame),
                             "source_rows": source_rows, "duplicate_rows_removed": source_rows - len(frame),
                             "birth_dates": int(frame.dob.ne("").sum()), "sha256": sha256(target)})
            path.unlink()
        print(f"{source_id}: {len(groups)} vintages", flush=True)
    staging.rmdir()
    catalogue = {"schema_version": 1, "sources": sources,
                 "vintages": sorted(vintages, key=lambda row: (row["season"], row["available_from"], row["id"]))}
    write_if_changed(output, (json.dumps(catalogue, ensure_ascii=False, indent=2) + "\n").encode())
    print(f"{len(vintages)} vintages; {sum(row['rows'] for row in vintages):,} player records")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=ROOT / ".cache/players")
    parser.add_argument("--output", type=Path, default=ROOT / "data/players/ea/vintages.json")
    parser.add_argument("--download", action="store_true", help="Download missing public ZIPs without credentials")
    args = parser.parse_args()
    build(args.cache, args.output, args.download)
