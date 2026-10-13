"""Append today's bookmaker 1X2 odds for the site competitions and the European cups to the dated archive.

Usage: python scripts/archive_odds.py [--out data/odds] [--regions eu] [--force]

Writes one CSV per competition and season (`data/odds/<season>/<code>.csv`), one row per fixture
and fetch, with `observed_at` set to the fetch time so a file can be passed as `--odds-snapshot`.
Each competition is fetched at most once per UTC day unless `--force`; a fetch costs one The Odds API
credit per region. Without ODDS_API_KEY (or ODDS_DATA_API_KEY) it skips and exits 0.
"""

import argparse
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from standing_prediction.odds import the_odds_api_snapshot
from standing_prediction.predict_positions import COMPETITION_TO_THE_ODDS_API_SPORT

# Europa and Conference League prices add cross-league fixtures between mid-table clubs (ROADMAP, item 1).
SPORTS = {**COMPETITION_TO_THE_ODDS_API_SPORT, "CL": "soccer_uefa_champs_league",
          "EL": "soccer_uefa_europa_league", "ECL": "soccer_uefa_europa_conference_league"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("data/odds"))
    parser.add_argument("--regions", default="eu", help="The Odds API regions; each one costs a credit per competition")
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
        if path.exists() and not args.force:
            fetched = pd.to_datetime(pd.read_csv(path, usecols=["fetched_at"])["fetched_at"], utc=True)
            if fetched.dt.date.eq(now.date()).any():
                print(f"{code}: already archived today")
                continue
        try:
            snapshot = the_odds_api_snapshot(sport_key=sport, competition=code, regions=args.regions, fetched_at=now)
        except (ValueError, OSError, RuntimeError) as exc:
            failed.append(code)
            print(f"{code}: odds unavailable ({type(exc).__name__})")
            continue
        if snapshot.empty:
            print(f"{code}: no fixtures quoted")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        # Append only, so earlier snapshots never change.
        snapshot.to_csv(path, mode="a", header=not path.exists(), index=False, float_format="%.5f")
        print(f"{code}: {len(snapshot)} fixtures, median {snapshot['books'].median():.0f} bookmakers")
    return 1 if len(failed) == len(SPORTS) else 0


if __name__ == "__main__":
    raise SystemExit(main())
