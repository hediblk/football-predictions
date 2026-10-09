from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class EloModel:
    ratings: Dict[str, float]
    k_factor: float = 30.0
    home_advantage: float = 55.0
    draw_base: float = 0.26
    draw_scale: float = 300.0

    def predict_probs(self, home, away):
        r_home = float(self.ratings.get(home, 1500.0))
        r_away = float(self.ratings.get(away, 1500.0))
        diff = (r_home + self.home_advantage) - r_away

        p_home_2way = 1.0 / (1.0 + 10.0 ** (-diff / 400.0))
        p_draw = float(self.draw_base * np.exp(-abs(diff) / max(self.draw_scale, 1e-6)))
        p_draw = float(np.clip(p_draw, 0.05, 0.35))

        p_home = float((1.0 - p_draw) * p_home_2way)
        p_away = float((1.0 - p_draw) * (1.0 - p_home_2way))
        total = p_home + p_draw + p_away
        if total <= 0:
            return 1 / 3, 1 / 3, 1 / 3
        return p_home / total, p_draw / total, p_away / total


def fit_elo(
    matches,
    *,
    teams=None,
    season_regression=0.75,
    k_factor=30.0,
    home_advantage=55.0,
    draw_base=None,
    draw_scale=300.0,
    initial_rating=1500.0,
):
    if not 0 <= season_regression <= 1:
        raise ValueError("season_regression must be between 0 and 1.")
    if not np.isfinite(draw_scale) or draw_scale <= 0:
        raise ValueError("draw_scale must be positive and finite.")
    required = {"homeTeam", "awayTeam", "homeGoals", "awayGoals"}
    missing = required - set(matches.columns)
    if missing:
        raise ValueError(f"matches is missing required columns: {sorted(missing)}")

    finished = matches.dropna(subset=["homeGoals", "awayGoals"]).copy()
    if finished.empty:
        raise ValueError("No finished matches available to fit Elo ratings.")

    if "utcDate" in finished.columns:
        finished["utcDate"] = pd.to_datetime(finished["utcDate"], utc=True)
        finished = finished.sort_values("utcDate")

    calibrate_draws = draw_base is None
    if calibrate_draws:
        draws = (finished["homeGoals"] == finished["awayGoals"]).mean()
        draw_target = float(np.clip(draws, 0.05, 0.35))
        draw_base = draw_target / max(np.exp(-abs(home_advantage) / draw_scale), 1e-12)

    observed_teams = pd.unique(finished[["homeTeam", "awayTeam"]].values.ravel("K"))
    ratings = {
        team: float(initial_rating)
        for team in [*observed_teams, *(teams if teams is not None else ())]
    }
    draw_decay = []
    previous_season = None

    def expected_home_score(p_home, p_draw):
        return p_home + 0.5 * p_draw

    for _, row in finished.iterrows():
        home = row["homeTeam"]
        away = row["awayTeam"]
        hg = int(row["homeGoals"])
        ag = int(row["awayGoals"])

        if "utcDate" in finished.columns:
            date = row["utcDate"]
            season = date.year - (date.month < 7)
            if previous_season is not None and season > previous_season:
                retained = season_regression ** (season - previous_season)
                ratings = {
                    team: float(initial_rating + retained * (rating - initial_rating))
                    for team, rating in ratings.items()
                }
            previous_season = season

        diff = ratings[home] + home_advantage - ratings[away]
        draw_decay.append(np.exp(-abs(diff) / draw_scale))
        model = EloModel(
            ratings=ratings,
            k_factor=k_factor,
            home_advantage=home_advantage,
            draw_base=float(draw_base),
            draw_scale=draw_scale,
        )
        p_home, p_draw, _p_away = model.predict_probs(home, away)
        exp_h = expected_home_score(p_home, p_draw)

        if hg > ag:
            act_h = 1.0
        elif hg == ag:
            act_h = 0.5
        else:
            act_h = 0.0

        delta = k_factor * (act_h - exp_h)
        ratings[home] = float(ratings.get(home, initial_rating) + delta)
        ratings[away] = float(ratings.get(away, initial_rating) - delta)

    if calibrate_draws:
        decay = np.array(draw_decay)
        lower, upper = 0.0, 1.0
        while np.clip(upper * decay, 0.05, 0.35).mean() < draw_target and upper < 1e6:
            upper *= 2
        for _ in range(50):
            baseline = (lower + upper) / 2
            if np.clip(baseline * decay, 0.05, 0.35).mean() < draw_target:
                lower = baseline
            else:
                upper = baseline
        draw_base = (lower + upper) / 2

    return EloModel(
        ratings=ratings,
        k_factor=k_factor,
        home_advantage=home_advantage,
        draw_base=float(draw_base),
        draw_scale=draw_scale,
    )
