import numpy as np
import pandas as pd
import pytest

from champions_league.strengths import fit_strengths

LEAGUES = {"A": 4, "B": 4, "C": 4, "D": 3}


def history(seed=1):
    """Strong league A beats B and C in Europe; sparse league D has one European draw with B."""
    rng = np.random.default_rng(seed)
    teams = {league: [f"{league}{i}" for i in range(size)] for league, size in LEAGUES.items()}
    rows, day = [], pd.Timestamp("2025-08-01", tz="UTC")

    def add(home, away, home_rate, away_rate, competition):
        nonlocal day
        rows.append({"utcDate": day, "homeTeam": home, "awayTeam": away, "competition": competition,
                     "homeGoals": int(rng.poisson(home_rate)), "awayGoals": int(rng.poisson(away_rate))})
        day += pd.Timedelta(hours=12)

    for _ in range(2):
        for league, members in teams.items():
            for home in members:
                for away in members:
                    if home != away:
                        add(home, away, 1.4, 1.1, league)
    for _ in range(6):
        for strong, weak in zip(teams["A"], teams["B"] + teams["C"]):
            add(strong, weak, 2.4, 0.5, "CL")
        for strong, weak in zip(teams["A"], teams["C"]):
            add(weak, strong, 0.6, 2.2, "CL")
    rows.append({"utcDate": day, "homeTeam": "D0", "awayTeam": "B0", "competition": "CL", "homeGoals": 1, "awayGoals": 1})
    return pd.DataFrame(rows), {team: league for league, members in teams.items() for team in members}, day + pd.Timedelta(days=1)


def test_sparse_league_shrinks_toward_typical_league_not_reference():
    data, leagues, origin = history()
    offsets = {prior: fit_strengths(data, teams=list(leagues), team_leagues=leagues, as_of=origin, xg_weight=0,
                                    offset_prior=prior).metadata["league_offsets"]
               for prior in ("reference", "fitted")}
    assert offsets["fitted"]["A"] == 0  # the best-connected league stays the reference
    assert offsets["fitted"]["B"] < -0.3 and offsets["fitted"]["C"] < -0.3
    # With one European draw, D sits near A under the old prior but with the weaker leagues under the new one.
    assert offsets["reference"]["D"] > -0.15
    assert offsets["fitted"]["D"] < offsets["reference"]["D"] - 0.15


def test_offset_prior_must_be_known():
    data, leagues, origin = history()
    with pytest.raises(ValueError, match="offset_prior"):
        fit_strengths(data, teams=list(leagues), team_leagues=leagues, as_of=origin, offset_prior="zero")
