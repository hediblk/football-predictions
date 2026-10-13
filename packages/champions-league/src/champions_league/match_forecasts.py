"""Per-match Champions League forecasts from the joint European model."""

from __future__ import annotations

import numpy as np
import pandas as pd

from standing_prediction.defaults import DEFAULT_WEIGHTS
from standing_prediction.ensemble import blend_probabilities
from standing_prediction.match_forecasts import describe_match, forecast_played, match_records

from champions_league.strengths import DEFAULT_OFFSET_RIDGE, fit_strengths
from champions_league.tournament import _neutral, _score

FIXTURE_COLUMNS = ["id", "utcDate", "stage", "matchday", "status", "homeTeam", "awayTeam", "homeTeamId", "awayTeamId",
                   "homeGoals", "awayGoals", "duration", "neutral"]


def fixture_forecasts(model, fixtures, forecast_at, max_goals=10):
    """The tournament simulation's 90-minute scoreline law for each fixture, without odds."""
    forecasts = []
    for row in fixtures.to_dict("records"):
        neutral = _neutral(row)
        _, matrix = model.score_matrix(row["homeTeam"], row["awayTeam"], max_goals=max_goals, neutral=neutral)
        matrix = matrix / matrix.sum()
        home, away = np.indices(matrix.shape)
        p_model = [matrix[mask].sum() for mask in (home > away, home == away, home < away)]
        p = blend_probabilities(p_model, p_elo=model.elo_probs(row["homeTeam"], row["awayTeam"], neutral=neutral),
                                weights=DEFAULT_WEIGHTS)
        forecasts.append({"forecast_at": pd.Timestamp(forecast_at).isoformat(), **describe_match(matrix, p, score=_score(row))})
    return forecasts


def match_forecasts(inputs, model, *, origin, offset_ridge=DEFAULT_OFFSET_RIDGE, market=None):
    """Every known fixture's forecast: unplayed ones from `model`, played ones refitted as of their match day."""
    fixtures = inputs.fixtures
    teams = inputs.standings["team"].tolist()
    played = fixtures[[_score(row) is not None for row in fixtures.to_dict("records")]]
    upcoming = fixtures.drop(index=played.index)
    forecasts = dict(zip(upcoming.index, fixture_forecasts(model, upcoming, origin)))

    def fit(day):
        history = inputs.history.copy()
        # Mirror the live rule: a result's xG is only known from the next UTC day.
        unknown = pd.to_datetime(history["utcDate"], utc=True).dt.normalize() + pd.Timedelta(days=1) >= day
        history.loc[unknown, [column for column in ("home_xg", "away_xg") if column in history]] = np.nan
        return fit_strengths(history, teams=teams, team_leagues=inputs.team_leagues, as_of=day, offset_ridge=offset_ridge,
                             market=market)

    forecasts.update(forecast_played(played, fit, fixture_forecasts))
    return match_records(fixtures, forecasts, FIXTURE_COLUMNS)
