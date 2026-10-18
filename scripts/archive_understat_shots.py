import argparse
import csv
import gzip
import io
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIELDS = ("match_id", "date", "home", "away", "side", "minute", "x", "y", "xg", "result", "situation", "body",
          "last_action", "player", "assister")


def match_shots(payload, match_id):
    rows = []
    for side in ("h", "a"):
        for shot in payload["shots"][side]:
            if shot["match_id"] != match_id or shot["h_a"] != side:
                raise ValueError("shot identity differs from requested match or side")
            rows.append([side, shot["minute"], shot["X"], shot["Y"], shot["xG"], shot["result"], shot["situation"],
                         shot["shotType"], shot["lastAction"], shot["player"], shot["player_assisted"] or ""])
    return sorted(rows, key=lambda row: int(row[1]))


def archive(index_path, cache_dir, out_dir, seasons):
    with gzip.open(index_path, "rt", newline="") as handle:
        games = [row for row in csv.DictReader(handle) if row["season"] in seasons and row["side"] == "h"]
    by_file = {}
    for game in sorted(games, key=lambda row: (row["date"], int(row["match_id"]))):
        cached = json.loads((cache_dir / f"{game['match_id']}.json").read_text())
        for shot in match_shots(json.loads(cached["content"]), game["match_id"]):
            by_file.setdefault((game["league"], game["season"]), []).append(
                [game["match_id"], game["date"], game["team"], game["opponent"], *shot])
    for (league, season), rows in sorted(by_file.items()):
        text = io.StringIO()
        writer = csv.writer(text, lineterminator="\n")
        writer.writerow(FIELDS)
        writer.writerows(rows)
        path = out_dir / league / f"{season}.csv.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as handle:
            handle.write(text.getvalue().encode())
        print(f"{league} {season}: {len({row[0] for row in rows})} matches, {len(rows)} shots")


def main():
    parser = argparse.ArgumentParser(description="Archive Understat shots from cached match payloads, without network access.")
    parser.add_argument("--seasons", nargs="+", default=["2025"])
    parser.add_argument("--index", type=Path, default=ROOT / "data/players/understat/team_games.csv.gz")
    parser.add_argument("--cache", type=Path, default=ROOT / ".cache/understat/matches")
    parser.add_argument("--out", type=Path, default=ROOT / "data/shots")
    args = parser.parse_args()
    archive(args.index, args.cache, args.out, set(args.seasons))


if __name__ == "__main__":
    main()
