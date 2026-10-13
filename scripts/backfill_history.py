"""Backfill the website's history files by rerunning the forecasts at past dates.

Usage: python scripts/backfill_history.py [--season 2026] [--end YYYY-MM-DD] [--dest site/data]
                                          [--only PL PD BL1 SA FL1 CL clubs] [--n-sim 10000]

Each day's forecast origin is the daily refresh time, 05:30 UTC, and only results available then
count (`football-predict --as-of`, `football-ucl --as-of`). Leagues are rerun on the morning of their
first match and on every later day that brings new results. The Champions League is rerun daily from
a week before its first league-phase match, and on every Monday from the first league weekend so the
weekly club ranking (history/<season>/clubs.json) starts with the season.

Progress is kept in `--work` (default out/backfill) after every day, so an interrupted run resumes
and a later run only adds the new days. At the end the backfill is merged into `--dest`, keeping any
points the daily refresh added after the backfilled range. Requires FOOTBALL_DATA_API_KEY.
"""

import argparse
import json
import logging
from pathlib import Path
import shutil
import sys

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site_data as site  # noqa: E402

from standing_prediction import site_history  # noqa: E402
from standing_prediction.data import RESULT_DELAY, FootballDataClient, fetch_matches  # noqa: E402

REFRESH = "05:30"
CLUBS = "clubs"


def origin(day):
    return pd.Timestamp(f"{day} {REFRESH}", tz="UTC")


def days_between(first, last):
    return [day.date().isoformat() for day in pd.date_range(first, last, freq="D")]


def result_days(kickoffs, end):
    """The first match day, plus every day whose refresh is the first to see a new result."""
    kickoffs = pd.to_datetime(pd.Series(kickoffs), utc=True).dropna().sort_values()
    if kickoffs.empty:
        return []
    days = {kickoffs.iloc[0].date().isoformat()}
    for available in kickoffs + RESULT_DELAY:
        day = available.normalize() if available <= available.normalize() + pd.Timedelta(REFRESH + ":00") else \
            available.normalize() + pd.Timedelta(days=1)
        days.add(day.date().isoformat())
    return sorted(day for day in days if day <= end)


def mondays(first, last):
    return [day for day in days_between(first, last) if pd.Timestamp(day).weekday() == 0]


def load(path):
    return json.loads(path.read_text()) if path.exists() else None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--end", default=pd.Timestamp.now(tz="UTC").date().isoformat(),
                        help="Last day to backfill (default: today; its 05:30 UTC refresh must have passed)")
    parser.add_argument("--dest", type=Path, default=Path("site/data"))
    parser.add_argument("--work", type=Path, default=Path("out/backfill"))
    parser.add_argument("--only", nargs="+", default=[league[1] for league in site.LEAGUES] + ["CL", CLUBS])
    parser.add_argument("--n-sim", type=int, default=10000)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    load_dotenv()
    from champions_league.cli import run_forecast
    from standing_prediction.predict_positions import run_prediction

    if origin(args.end) > pd.Timestamp.now(tz="UTC"):
        parser.error(f"The {REFRESH} UTC refresh of {args.end} has not happened yet.")
    # Reuse downloads for half a day: a backfill takes longer than the usual one-hour cache.
    client = FootballDataClient(max_age=12 * 3600)
    leagues = [league for league in site.LEAGUES if league[1] in args.only]
    current = {league[0]: load(args.dest / f"{league[0]}.json") for league in site.LEAGUES}
    season_label = f"{args.season}/{str(args.season + 1)[-2:]}"
    history_dir = args.work / "history" / str(args.season)
    runs = args.work / "runs"

    schedule = {}
    first_league_day = None
    for slug, code, *_ in site.LEAGUES:
        matches = fetch_matches(client, competition=code, season=args.season, status=None)
        kickoffs = matches.loc[matches["status"].eq("FINISHED"), "utcDate"]
        first = matches["utcDate"].min().date().isoformat()
        first_league_day = min(first_league_day or first, first)
        if code in args.only:
            schedule[slug] = result_days(pd.concat([kickoffs, pd.Series([matches["utcDate"].min()])]), args.end)
    cl_matches = fetch_matches(client, competition="CL", season=args.season, status=None)
    cl_first = (cl_matches["utcDate"].min() - pd.Timedelta(days=7)).date().isoformat()
    if "CL" in args.only:
        schedule["champions-league"] = days_between(cl_first, args.end)
    if CLUBS in args.only:
        schedule[CLUBS] = mondays(first_league_day, args.end)

    histories = {slug: load(history_dir / f"{slug}.json") for slug in schedule}
    done = {slug: (history or {}).get("dates", [""])[-1] if slug != CLUBS else
            ((history or {}).get("weeks") or [{"date": ""}])[-1]["date"] for slug, history in histories.items()}
    days = sorted({day for slug, days in schedule.items() for day in days if day > done[slug]})
    print(f"Backfilling {len(days)} days: " + ", ".join(f"{slug} {sum(d > done[slug] for d in schedule[slug])}"
                                                       for slug in schedule))

    def save(slug, history):
        histories[slug] = history
        history_dir.mkdir(parents=True, exist_ok=True)
        site.write_json(history_dir / f"{slug}.json", history)

    for day in days:
        when = origin(day)
        for slug, code, *rest in leagues:
            if day in schedule[slug] and day > done[slug]:
                run_prediction(competition=code, season=args.season, n_sim=args.n_sim, use_odds=False,
                               match_forecasts=False, as_of=when, client=client, out_dir=runs)
                save(slug, site_history.add_point(histories[slug], site.export_league(runs, slug, code, *rest), day))
        ucl_day = day in schedule.get("champions-league", []) and day > done["champions-league"]
        club_day = day in schedule.get(CLUBS, []) and day > done[CLUBS]
        if ucl_day or club_day:
            run_forecast(season=args.season, as_of=when, n_sim=args.n_sim, out_dir=runs, sensitivity=False,
                         match_forecasts=False, client=client)
            ucl = site.export_ucl(runs)
            if ucl_day:
                save("champions-league", site_history.add_point(histories["champions-league"], ucl, day))
            if club_day:
                ratings = site.rated_clubs(runs, [data for data in current.values() if data], ucl)
                history, _ = site_history.freeze_week(histories[CLUBS], ratings, as_of=when, season=season_label,
                                                      cutoff=ucl["data_cutoff"])
                save(CLUBS, history)
        shutil.rmtree(runs / "snapshots", ignore_errors=True)
        print(f"{day} done", flush=True)

    for slug, history in histories.items():
        if not history:
            continue
        path = args.dest / "history" / str(args.season) / f"{slug}.json"
        existing = load(path)
        merged = site_history.merge_weeks(history, existing) if slug == CLUBS else site_history.merge_points(history, existing)
        site.write_json(path, merged)
        print(f"Wrote {path} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
