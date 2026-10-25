"""Append today's bookmaker 1X2 odds for the site competitions and the European cups to the dated archive.

Usage: python scripts/archive_odds.py [--out data/odds] [--regions eu] [--force]

Writes one CSV per competition and season (`data/odds/<season>/<code>.csv`), one row per fixture
and fetch, with `observed_at` set to the fetch time so a file can be passed as `--odds-snapshot`.
For the five domestic leagues it also writes raw 1X2 and 2.5 totals prices to `<code>_prices.csv`.
Each competition is fetched at most once per UTC day unless `--force`. The script reports The Odds API
quota headers when available. Without ODDS_API_KEY (or ODDS_DATA_API_KEY) it skips and exits 0.
"""

import argparse
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from standing_prediction.odds import the_odds_api_archive_snapshots
from standing_prediction.predict_positions import COMPETITION_TO_THE_ODDS_API_SPORT

# Europa and Conference League prices add cross-league fixtures between mid-table clubs (ROADMAP, item 1).
SPORTS = {**COMPETITION_TO_THE_ODDS_API_SPORT, "CL": "soccer_uefa_champs_league",
          "EL": "soccer_uefa_europa_league", "ECL": "soccer_uefa_europa_conference_league"}
DOMESTIC = set(COMPETITION_TO_THE_ODDS_API_SPORT)


def _archived_today(path, date):
    if not path.exists():
        return False
    fetched = pd.to_datetime(pd.read_csv(path, usecols=["fetched_at"])["fetched_at"], utc=True)
    return fetched.dt.date.eq(date).any()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("data/odds"))
    parser.add_argument("--regions", default="eu", help="The Odds API regions to request")
    parser.add_argument("--force", action="store_true", help="Fetch even if today's snapshot is already archived")
    args = parser.parse_args(argv)
    load_dotenv()
    if not (os.getenv("ODDS_API_KEY") or os.getenv("ODDS_DATA_API_KEY")):
        print("ODDS_API_KEY is not set; skipping the odds archive.")
        return 0
    now = pd.Timestamp.now(tz="UTC")
    season = now.year if now.month >= 7 else now.year - 1
    failed = []
    for code, sport in SPORTS.items():
        path = args.out / str(season) / f"{code}.csv"
        price_path = path.with_name(f"{code}_prices.csv")
        need_prices = code in DOMESTIC
        has_snapshot_today = _archived_today(path, now.date())
        if not args.force and has_snapshot_today and (not need_prices or _archived_today(price_path, now.date())):
            print(f"{code}: already archived today")
            continue
        quota_headers = {}
        try:
            if need_prices:
                snapshot, prices = the_odds_api_archive_snapshots(
                    sport_key=sport, competition=code, regions=args.regions, fetched_at=now, markets="h2h,totals",
                    on_response_headers=quota_headers.update,
                )
            else:
                snapshot, _ = the_odds_api_archive_snapshots(
                    sport_key=sport, competition=code, regions=args.regions, fetched_at=now,
                    on_response_headers=quota_headers.update,
                )
        except (ValueError, OSError, RuntimeError) as exc:
            failed.append(code)
            print(f"{code}: odds unavailable ({type(exc).__name__})")
            continue
        usage = " ".join(f"{key.removeprefix('x-requests-')}={quota_headers[key]}"
                         for key in ("x-requests-last", "x-requests-used", "x-requests-remaining")
                         if quota_headers.get(key) is not None)
        if usage:
            print(f"{code}: The Odds API quota {usage}")
        if snapshot.empty:
            if need_prices and not prices.empty:
                path.parent.mkdir(parents=True, exist_ok=True)
                prices.to_csv(price_path, mode="a", header=not price_path.exists(), index=False, float_format="%.5f")
                print(f"{code}: no 1X2 quotes; archived {len(prices)} raw price rows")
                continue
            print(f"{code}: no fixtures quoted")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        # Append only, so earlier snapshots never change.
        if args.force or not has_snapshot_today:
            snapshot.to_csv(path, mode="a", header=not path.exists(), index=False, float_format="%.5f")
        if need_prices and not prices.empty:
            prices.to_csv(price_path, mode="a", header=not price_path.exists(), index=False, float_format="%.5f")
        print(f"{code}: {len(snapshot)} fixtures, median {snapshot['books'].median():.0f} bookmakers")
    return 1 if len(failed) == len(SPORTS) else 0


if __name__ == "__main__":
    raise SystemExit(main())
