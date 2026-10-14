import argparse
import csv
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import time

import requests


SPORTS = {"EL": "uefa.europa", "ECL": "uefa.europa.conf"}
COLUMNS = ["fetched_at", "competition", "espn_id", "kickoff", "stage", "home_team",
           "away_team", "home_goals", "away_goals", "status", "shootout_winner"]
STATUSES = {"STATUS_FULL_TIME": "full time", "STATUS_FINAL_AET": "after extra time",
            "STATUS_FINAL_PEN": "penalties"}


def fetch_scoreboard(session, sport, day, last_request):
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{sport}/scoreboard"
    for attempt in range(3):
        time.sleep(max(0, 1 - (time.monotonic() - last_request[0])))
        last_request[0] = time.monotonic()
        try:
            response = session.get(url, params={"dates": day.strftime("%Y%m%d")}, timeout=30)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def result_row(event, code, fetched_at):
    match = event["competitions"][0]
    status = match["status"]["type"]
    name = status["name"]
    if not status.get("completed") or name not in STATUSES:
        if status.get("completed") or any(word in name for word in ("POSTPON", "CANCEL", "ABANDON", "SUSPEND")):
            print(f"{code} {event['id']}: skipped {name}", flush=True)
        return None
    sides = {team["homeAway"]: team for team in match["competitors"]}
    home, away = sides["home"], sides["away"]
    home_name, away_name = home["team"]["displayName"], away["team"]["displayName"]
    home_goals, away_goals = int(home["score"]), int(away["score"])
    if min(home_goals, away_goals) < 0:
        raise ValueError("negative score")
    kickoff = datetime.fromisoformat(match["date"].replace("Z", "+00:00"))
    if kickoff.tzinfo is None:
        raise ValueError("kickoff has no timezone")
    winner = ""
    if name == "STATUS_FINAL_PEN":
        home_pens, away_pens = int(home["shootoutScore"]), int(away["shootoutScore"])
        if min(home_pens, away_pens) < 0 or home_pens == away_pens:
            raise ValueError("invalid shootout score")
        winner = home_name if home_pens > away_pens else away_name
    return dict(zip(COLUMNS, [fetched_at, code, str(event["id"]), kickoff.astimezone(timezone.utc).isoformat(),
                              event["season"]["slug"], home_name, away_name, home_goals, away_goals,
                              STATUSES[name], winner]))


def archive(args):
    seen = set()
    for path in args.out.glob("*/*.csv"):
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != COLUMNS:
                raise ValueError(f"unexpected columns in {path}")
            seen.update(row["espn_id"] for row in reader)
    added, failed = 0, 0
    last_request = [0.0]
    with requests.Session() as session:
        day = args.start
        while day <= args.end:
            for code, sport in SPORTS.items():
                try:
                    payload = fetch_scoreboard(session, sport, day, last_request)
                    events = payload["events"]
                    fetched_at = datetime.now(timezone.utc).isoformat()
                except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                    failed += 1
                    print(f"{code} {day}: fetch failed ({type(exc).__name__}); continuing", flush=True)
                    continue
                count = 0
                for event in events:
                    try:
                        if str(event["id"]) in seen:
                            continue
                        row = result_row(event, code, fetched_at)
                        if row is None:
                            continue
                        kickoff = datetime.fromisoformat(row["kickoff"])
                        season = kickoff.year - (kickoff.month < 7)
                        path = args.out / str(season) / f"{code}.csv"
                        path.parent.mkdir(parents=True, exist_ok=True)
                        with path.open("a", newline="", encoding="utf-8") as handle:
                            writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
                            if handle.tell() == 0:
                                writer.writeheader()
                            writer.writerow(row)
                        seen.add(row["espn_id"])
                        count += 1
                    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
                        print(f"{code} {day} {event.get('id', '?')}: skipped ({type(exc).__name__}: {exc})", flush=True)
                added += count
                if events:
                    print(f"{code} {day}: {len(events)} events, {count} appended", flush=True)
            if day.day == 1:
                print(f"Scanned through {day}", flush=True)
            day += timedelta(days=1)
    print(f"Results archive: {added} appended, {failed} failed daily requests", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Append finished Europa and Conference League results from ESPN.")
    parser.add_argument("--from", dest="start", type=date.fromisoformat, help="First UTC date, inclusive (YYYY-MM-DD)")
    parser.add_argument("--to", dest="end", type=date.fromisoformat, help="Last UTC date, inclusive (YYYY-MM-DD)")
    parser.add_argument("--out", type=Path, default=Path("data/results"))
    args = parser.parse_args(argv)
    if (args.start is None) != (args.end is None):
        parser.error("--from and --to must be supplied together")
    today = datetime.now(timezone.utc).date()
    args.start, args.end = args.start or today - timedelta(days=6), args.end or today
    if args.start > args.end:
        parser.error("--from must not be after --to")
    try:
        archive(args)
    except Exception as exc:
        print(f"Results archive unavailable ({type(exc).__name__}: {exc}); refresh may continue", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
