from datetime import datetime

import numpy as np
import pytest

from standing_prediction.club_ratings import club_ratings
from standing_prediction.dixon_coles import DixonColesModel

TEAMS = ("Top", "Mid", "Low", "Bottom")


def model():
    return DixonColesModel(teams=TEAMS, team_index={team: i for i, team in enumerate(TEAMS)}, intercept=0.2,
                           home_advantage=0.25, attack=np.array([0.5, 0.1, -0.2, -0.4]),
                           defense=np.array([-0.4, 0.0, 0.1, 0.3]), rho=-0.05, xi=0.003, fitted_at=datetime(2026, 1, 1))


def test_default_reference_is_the_rated_clubs_own_average():
    dc = model()
    assert club_ratings(dc, TEAMS).equals(club_ratings(dc, TEAMS, reference=TEAMS))
    average = club_ratings(dc, TEAMS).set_index("team")
    # Against its own average, the average club would take about half of a typical points share.
    assert 0 < average.loc["Bottom", "rating"] < average.loc["Top", "rating"] < 100


def test_a_weaker_reference_raises_every_rating_and_keeps_the_order():
    dc = model()
    own = club_ratings(dc, TEAMS[:2]).set_index("team")
    wide = club_ratings(dc, TEAMS[:2], reference=TEAMS).set_index("team")
    assert (wide["rating"] > own["rating"]).all()
    assert list(wide.index) == list(own.index) == ["Top", "Mid"]
    assert wide.loc["Top", "goals_for"] == pytest.approx(np.exp(0.2 + 0.5 + 0.0))  # mean defense of all four is 0
