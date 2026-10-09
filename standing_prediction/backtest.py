from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.model_selection import GroupKFold

from standing_prediction.data import FootballDataClient, fetch_matches
from standing_prediction.dixon_coles import fit_dixon_coles
from standing_prediction.elo import fit_elo
from standing_prediction.odds import (
    COMPETITION_TO_FOOTBALL_DATA_UK_LEAGUE,
    fetch_football_data_uk_matches,
    fetch_football_data_uk_probs,
)
from standing_prediction.utils import normalize_team


@dataclass(frozen=True)
class BacktestRow:
    season: int
    p_dc: Tuple[float, float, float]
    p_elo: Tuple[float, float, float]
    p_book: Optional[Tuple[float, float, float]]
    y: int  # 0 home, 1 draw, 2 away


def main(argv=None):
    parser = argparse.ArgumentParser(description="Backtest match-probability models on past seasons.")
    parser.add_argument("--competition", default="PD", help="football-data.org competition code (default: PD)")
    parser.add_argument(
        "--seasons",
        nargs="+",
        type=int,
        required=True,
        help="Season start years to backtest, e.g. 2022 2023 2024",
    )
    parser.add_argument("--cutoff-matchday", type=int, default=10, help="Train on <= cutoff matchday")
    parser.add_argument("--xi", type=float, default=0.003, help="Dixon–Coles time decay")
    parser.add_argument("--lambda-reg", type=float, default=0.1, help="Dixon–Coles L2 regularization")
    parser.add_argument(
        "--use-odds",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include football-data.co.uk odds when available (default: true)",
    )
    args = parser.parse_args(argv)

    load_dotenv(".env")
    client = FootballDataClient()

    rows: List[BacktestRow] = []
    for season in args.seasons:
        season_rows = backtest_season(
            client,
            competition=args.competition,
            season=season,
            cutoff_matchday=int(args.cutoff_matchday),
            xi=float(args.xi),
            lambda_reg=float(args.lambda_reg),
            use_odds=bool(args.use_odds),
        )
        rows.extend(season_rows)
        print(f"Season {season}: {len(season_rows)} matches evaluated")

    if not rows:
        raise SystemExit("No backtest rows produced.")

    df = _rows_to_frame(rows)
    print()
    _print_baselines(df)
    print()
    _print_calibrated_ensemble(df)
    return 0


def backtest_season(
    client,
    *,
    competition,
    season,
    cutoff_matchday,
    xi,
    lambda_reg,
    use_odds,
):
    league = COMPETITION_TO_FOOTBALL_DATA_UK_LEAGUE.get(competition)
    try:
        matches = fetch_matches(client, competition=competition, season=season, status="FINISHED")
    except Exception:
        if not league:
            return []
        matches = fetch_football_data_uk_matches(league_code=league, season_start_year=season)
    if matches.empty:
        return []

    train = matches[matches["matchday"].fillna(0).astype(int) <= cutoff_matchday].copy()
    test = matches[matches["matchday"].fillna(0).astype(int) > cutoff_matchday].copy()
    if train.empty or test.empty:
        return []

    dc = fit_dixon_coles(train, xi=xi, lambda_reg=lambda_reg)
    elo = fit_elo(train)

    odds_lookup: Optional[pd.DataFrame] = None
    if use_odds and league:
        try:
            odds = fetch_football_data_uk_probs(league_code=league, season_start_year=season)
            odds_lookup = odds.set_index(["home_norm", "away_norm"])[
                ["p_home_book", "p_draw_book", "p_away_book"]
            ]
        except Exception:
            odds_lookup = None

    rows: List[BacktestRow] = []
    for _, row in test.iterrows():
        home = str(row["homeTeam"])
        away = str(row["awayTeam"])
        hg = int(row["homeGoals"])
        ag = int(row["awayGoals"])

        p_dc = dc.match_outcome_probs(home, away, max_goals=10)
        p_elo = elo.predict_probs(home, away)

        p_book = None
        if odds_lookup is not None:
            hn = normalize_team(home)
            an = normalize_team(away)
            if (hn, an) in odds_lookup.index:
                r = odds_lookup.loc[(hn, an)]
                p_book = (float(r["p_home_book"]), float(r["p_draw_book"]), float(r["p_away_book"])) # type: ignore

        if hg > ag:
            y = 0
        elif hg == ag:
            y = 1
        else:
            y = 2

        rows.append(BacktestRow(season=season, p_dc=p_dc, p_elo=p_elo, p_book=p_book, y=y))

    return rows


def _rows_to_frame(rows):
    data = []
    for r in rows:
        p_book = r.p_book or (np.nan, np.nan, np.nan)
        data.append(
            {
                "season": r.season,
                "y": r.y,
                "dc_h": r.p_dc[0],
                "dc_d": r.p_dc[1],
                "dc_a": r.p_dc[2],
                "elo_h": r.p_elo[0],
                "elo_d": r.p_elo[1],
                "elo_a": r.p_elo[2],
                "book_h": p_book[0],
                "book_d": p_book[1],
                "book_a": p_book[2],
            }
        )
    return pd.DataFrame(data)


def _print_baselines(df):
    y = df["y"].to_numpy(dtype=int)

    p_dc = df[["dc_h", "dc_d", "dc_a"]].to_numpy(dtype=float)
    p_elo = df[["elo_h", "elo_d", "elo_a"]].to_numpy(dtype=float)
    print(f"Log loss (DC):  {log_loss(y, p_dc, labels=[0, 1, 2]):.4f}")
    print(f"Log loss (Elo): {log_loss(y, p_elo, labels=[0, 1, 2]):.4f}")

    has_book = df[["book_h", "book_d", "book_a"]].notna().all(axis=1)
    if has_book.any():
        p_book = df.loc[has_book, ["book_h", "book_d", "book_a"]].to_numpy(dtype=float)
        y_book = df.loc[has_book, "y"].to_numpy(dtype=int)
        print(f"Log loss (Odds): {log_loss(y_book, p_book, labels=[0, 1, 2]):.4f} (n={len(y_book)})")
    else:
        print("Log loss (Odds): n/a (no odds matched)")


def _print_calibrated_ensemble(df):
    y = df["y"].to_numpy(dtype=int)
    groups = df["season"].to_numpy(dtype=int)

    # Feature set that works without odds (always present).
    x_basic = df[["dc_h", "dc_d", "dc_a", "elo_h", "elo_d", "elo_a"]].to_numpy(dtype=float)

    # Odds features if available; fill missing with 1/3.
    x_odds = df[["book_h", "book_d", "book_a"]].to_numpy(dtype=float)
    x_odds = np.where(np.isfinite(x_odds), x_odds, 1.0 / 3.0)

    X = np.concatenate([x_basic, x_odds], axis=1)

    n_groups = len(np.unique(groups))
    if n_groups < 2:
        model = LogisticRegression(max_iter=2000, solver="lbfgs")
        model.fit(X, y)
        p = model.predict_proba(X)
        print(f"Log loss (Calibrated ensemble, no-CV): {log_loss(y, p, labels=[0, 1, 2]):.4f}")
        return

    cv = GroupKFold(n_splits=min(5, n_groups))
    losses = []
    for train_idx, test_idx in cv.split(X, y, groups=groups):
        model = LogisticRegression(max_iter=2000, solver="lbfgs")
        model.fit(X[train_idx], y[train_idx])
        p = model.predict_proba(X[test_idx])
        losses.append(log_loss(y[test_idx], p, labels=[0, 1, 2]))

    print(f"Log loss (Calibrated ensemble, CV by season): {float(np.mean(losses)):.4f}")


if __name__ == "__main__":
    raise SystemExit(main())
