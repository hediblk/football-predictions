from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

from standing_prediction.calibration import train_outcome_calibrator
from standing_prediction.data import FootballDataClient, fetch_matches, fetch_standings
from standing_prediction.dixon_coles import fit_dixon_coles
from standing_prediction.elo import fit_elo
from standing_prediction.ensemble import blend_probabilities
from standing_prediction.odds import (
    COMPETITION_TO_FOOTBALL_DATA_UK_LEAGUE,
    fetch_football_data_uk_matches,
    fetch_football_data_uk_probs,
    fetch_the_odds_api_h2h_probs,
)
from standing_prediction.simulate import FixtureSimulationSpec, simulate_season_scores
from standing_prediction.utils import normalize_team


COMPETITION_TO_THE_ODDS_API_SPORT = {
    "PD": "soccer_spain_la_liga",
    "PL": "soccer_epl",
    "BL1": "soccer_germany_bundesliga",
    "SA": "soccer_italy_serie_a",
    "FL1": "soccer_france_ligue_one",
}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Predict league position probabilities via simulation.")
    parser.add_argument("--competition", default="PD", help="football-data.org competition code (default: PD)")
    parser.add_argument("--season", type=int, default=None, help="Season start year, e.g. 2025 for 2025/26")
    parser.add_argument("--n-sim", type=int, default=3000, help="Number of season simulations (default: 3000)")
    parser.add_argument("--seed", type=int, default=7, help="RNG seed (default: 7)")
    parser.add_argument("--max-goals", type=int, default=10, help="Max goals truncation for score matrix (default: 10)")
    parser.add_argument("--xi", type=float, default=0.003, help="Time-decay rate for Dixon–Coles (default: 0.003)")
    parser.add_argument("--lambda-reg", type=float, default=0.1, help="L2 regularization for DC params (default: 0.1)")

    parser.add_argument(
        "--use-odds",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Blend bookmaker odds into match probabilities when available (default: true)",
    )
    parser.add_argument(
        "--odds-provider",
        choices=["the_odds_api", "football_data_uk", "none"],
        default="the_odds_api",
        help="Odds provider to use (default: the_odds_api)",
    )
    parser.add_argument("--odds-days", type=int, default=180, help="How many future days to request from The Odds API")

    parser.add_argument("--out-dir", type=str, default="./out", help="Output directory")
    parser.add_argument(
        "--weights",
        type=str,
        default="main=0.35,odds=0.55,elo=0.10",
        help="Ensemble weights as key=val CSV (default: main=0.35,odds=0.55,elo=0.10)",
    )

    parser.add_argument(
        "--calibrate",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Train a multinomial calibrator on past seasons and use it for match probabilities (default: false)",
    )
    parser.add_argument(
        "--calibration-seasons",
        nargs="*",
        type=int,
        default=None,
        help="Season start years to train calibration on (default: previous 3 seasons)",
    )
    parser.add_argument(
        "--calibration-cutoff-matchday",
        type=int,
        default=10,
        help="Train base models on <= cutoff matchday when generating calibration rows",
    )

    args = parser.parse_args(argv)

    load_dotenv(".env")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    client = FootballDataClient()
    standings = fetch_standings(client, competition=args.competition, season=args.season)
    standings = standings.sort_values("position").reset_index(drop=True)

    finished = fetch_matches(client, competition=args.competition, season=args.season, status="FINISHED")
    remaining = fetch_matches(
        client, competition=args.competition, season=args.season, status="SCHEDULED,TIMED"
    )

    if remaining.empty:
        raise SystemExit("No remaining fixtures found (SCHEDULED,TIMED).")

    dc = fit_dixon_coles(finished, xi=float(args.xi), lambda_reg=float(args.lambda_reg))
    elo = fit_elo(finished)

    odds = None
    if args.use_odds and args.odds_provider != "none":
        odds = _load_odds(
            competition=args.competition,
            season=args.season,
            remaining=remaining,
            provider=args.odds_provider,
            days=int(args.odds_days),
        )

    weights = _parse_weights(args.weights)
    calibrator = None
    if args.calibrate:
        calib_seasons = args.calibration_seasons
        if not calib_seasons:
            season_start = args.season if args.season is not None else _guess_season_start_year()
            calib_seasons = [season_start - 3, season_start - 2, season_start - 1]
        calibrator = _train_calibrator(
            client,
            competition=args.competition,
            seasons=list(calib_seasons),
            cutoff_matchday=int(args.calibration_cutoff_matchday),
            xi=float(args.xi),
            lambda_reg=float(args.lambda_reg),
        )
    fixtures_specs = build_fixture_specs(
        remaining,
        dc=dc,
        elo=elo,
        odds=odds,
        max_goals=int(args.max_goals),
        weights=weights,
        calibrator=calibrator,
    )

    counts = simulate_season_scores(fixtures_specs, standings, n_sim=int(args.n_sim), seed=args.seed)
    probs = (counts / float(args.n_sim)) * 100.0

    probs_path = out_dir / f"{args.competition.lower()}_position_probs.csv"
    probs.to_csv(probs_path, float_format="%.4f")

    html_path = out_dir / f"{args.competition.lower()}_position_probs.html"
    _write_html(probs, standings=standings, path=html_path)

    print(f"Wrote {probs_path}")
    print(f"Wrote {html_path}")
    return 0


def build_fixture_specs(
    remaining,
    *,
    dc,
    elo,
    odds,
    max_goals,
    weights,
    calibrator=None,
):
    scorelines = _scoreline_grid(max_goals)
    mask_home = scorelines[:, 0] > scorelines[:, 1]
    mask_draw = scorelines[:, 0] == scorelines[:, 1]
    mask_away = scorelines[:, 0] < scorelines[:, 1]

    odds_lookup = None
    if odds is not None and not odds.empty:
        odds_lookup = odds.set_index(["home_norm", "away_norm"])[
            ["p_home_book", "p_draw_book", "p_away_book"]
        ]

    specs = []
    for _, row in remaining.iterrows():
        home = str(row["homeTeam"])
        away = str(row["awayTeam"])

        p_dc = dc.match_outcome_probs(home, away, max_goals=max_goals)
        p_elo = elo.predict_probs(home, away)

        p_odds = None
        if odds_lookup is not None:
            hn = normalize_team(home)
            an = normalize_team(away)
            if (hn, an) in odds_lookup.index:
                r = odds_lookup.loc[(hn, an)]
                p_odds = (float(r["p_home_book"]), float(r["p_draw_book"]), float(r["p_away_book"])) # type: ignore

        if calibrator is not None:
            p_blend = calibrator.predict_probs(p_dc=p_dc, p_elo=p_elo, p_book=p_odds)
        else:
            p_blend = blend_probabilities(p_dc, p_odds=p_odds, p_elo=p_elo, weights=weights)

        _, matrix = dc.score_matrix(home, away, max_goals=max_goals)
        p_flat = matrix.reshape(-1)

        probs_home = _conditional_probs(p_flat, mask_home)
        probs_draw = _conditional_probs(p_flat, mask_draw)
        probs_away = _conditional_probs(p_flat, mask_away)

        specs.append(
            FixtureSimulationSpec(
                home=home,
                away=away,
                p_home_win=p_blend[0],
                p_draw=p_blend[1],
                p_away_win=p_blend[2],
                scorelines=scorelines,
                score_probs_by_outcome=(probs_home, probs_draw, probs_away),
            )
        )

    return specs


def _conditional_probs(p_flat, mask):
    probs = p_flat * mask.astype(float)
    s = float(probs.sum())
    if s > 0:
        return probs / s
    idx = np.flatnonzero(mask)
    if len(idx) == 0:
        return np.ones_like(p_flat) / len(p_flat)
    out = np.zeros_like(p_flat)
    out[idx] = 1.0 / len(idx)
    return out


def _scoreline_grid(max_goals):
    goals = np.arange(max_goals + 1, dtype=int)
    home, away = np.meshgrid(goals, goals, indexing="ij")
    return np.stack([home.reshape(-1), away.reshape(-1)], axis=1)


def _parse_weights(spec):
    weights = {}
    for part in str(spec).split(","):
        if not part.strip():
            continue
        k, v = part.split("=", 1)
        weights[k.strip()] = float(v.strip())
    return weights


def _load_odds(
    *,
    competition,
    season,
    remaining,
    provider,
    days,
):
    if provider == "the_odds_api":
        sport_key = COMPETITION_TO_THE_ODDS_API_SPORT.get(competition)
        if not sport_key:
            return None
        try:
            return fetch_the_odds_api_h2h_probs(sport_key=sport_key, days=days)
        except Exception:
            return None

    if provider == "football_data_uk":
        if season is None:
            # football-data.co.uk requires season start year.
            return None
        league = COMPETITION_TO_FOOTBALL_DATA_UK_LEAGUE.get(competition)
        if not league:
            return None
        try:
            df = fetch_football_data_uk_probs(league_code=league, season_start_year=season)
        except Exception:
            return None
        # Keep only rows that match remaining fixtures by normalized names.
        rem = remaining.copy()
        rem["home_norm"] = rem["homeTeam"].astype(str).apply(normalize_team)
        rem["away_norm"] = rem["awayTeam"].astype(str).apply(normalize_team)
        df = df.merge(rem[["home_norm", "away_norm"]].drop_duplicates(), on=["home_norm", "away_norm"], how="inner")
        return df

    return None


def _write_html(probs, *, standings, path):
    order = standings["team"].tolist()
    probs = probs.reindex(order)
    expected_pos = (probs.mul(np.array(probs.columns, dtype=float), axis=1).sum(axis=1) / 100.0).round(2)

    out = probs.copy()
    out.insert(0, "expected_pos", expected_pos)

    styler = (
        out.style.format("{:.2f}", subset=["expected_pos"])
        .format("{:.1f}%", subset=[c for c in out.columns if c != "expected_pos"])
        .background_gradient(cmap="YlGn", subset=[c for c in out.columns if c != "expected_pos"])
        .set_table_styles(
            [
                {"selector": "th", "props": [("text-align", "center"), ("font-family", "Arial")]},
                {"selector": "td", "props": [("text-align", "center"), ("font-family", "Arial")]},
                {"selector": "caption", "props": [("caption-side", "top"), ("font-size", "18px")]},
            ]
        )
    )
    html = styler.to_html()
    path.write_text(html, encoding="utf-8")


def _train_calibrator(
    client,
    *,
    competition,
    seasons,
    cutoff_matchday,
    xi,
    lambda_reg,
):
    rows = []
    league = COMPETITION_TO_FOOTBALL_DATA_UK_LEAGUE.get(competition)
    for season in seasons:
        try:
            matches = fetch_matches(client, competition=competition, season=season, status="FINISHED")
        except Exception:
            if not league:
                continue
            matches = fetch_football_data_uk_matches(league_code=league, season_start_year=season)
        if matches.empty:
            continue

        train = matches[matches["matchday"].fillna(0).astype(int) <= cutoff_matchday].copy()
        test = matches[matches["matchday"].fillna(0).astype(int) > cutoff_matchday].copy()
        if train.empty or test.empty:
            continue

        dc = fit_dixon_coles(train, xi=xi, lambda_reg=lambda_reg)
        elo = fit_elo(train)

        odds_lookup = None
        if league:
            try:
                odds = fetch_football_data_uk_probs(league_code=league, season_start_year=season)
                odds_lookup = odds.set_index(["home_norm", "away_norm"])[
                    ["p_home_book", "p_draw_book", "p_away_book"]
                ]
            except Exception:
                odds_lookup = None

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
                    p_book = (
                        float(r["p_home_book"]), # type: ignore
                        float(r["p_draw_book"]), # type: ignore
                        float(r["p_away_book"]), # type: ignore
                    )

            if hg > ag:
                y = 0
            elif hg == ag:
                y = 1
            else:
                y = 2

            rows.append(
                {
                    "y": y,
                    "dc_h": p_dc[0],
                    "dc_d": p_dc[1],
                    "dc_a": p_dc[2],
                    "elo_h": p_elo[0],
                    "elo_d": p_elo[1],
                    "elo_a": p_elo[2],
                    "book_h": p_book[0] if p_book else np.nan,
                    "book_d": p_book[1] if p_book else np.nan,
                    "book_a": p_book[2] if p_book else np.nan,
                }
            )

    if not rows:
        raise ValueError("Calibration requested, but no training rows were produced.")

    df = pd.DataFrame(rows)
    return train_outcome_calibrator(df, use_odds_features=True)


def _guess_season_start_year():
    today = pd.Timestamp.utcnow()
    # Most European leagues run Aug/Sept -> May/June. Use July as a simple cutover.
    return int(today.year if today.month >= 7 else today.year - 1)


if __name__ == "__main__":
    raise SystemExit(main())
