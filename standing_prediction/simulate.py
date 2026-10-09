from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FixtureSimulationSpec:
    home: str
    away: str
    p_home_win: float
    p_draw: float
    p_away_win: float
    scorelines: np.ndarray
    score_probs_by_outcome: tuple[np.ndarray, np.ndarray, np.ndarray]


def _integers(values, name, *, nonnegative=True):
    values = np.asarray(values, dtype=float)
    if not np.isfinite(values).all() or (values != np.floor(values)).any():
        raise ValueError(f"{name} must contain finite integers.")
    if (values >= 2**63).any() or (values < -(2**63)).any():
        raise ValueError(f"{name} exceeds the supported integer range.")
    if nonnegative and (values < 0).any():
        raise ValueError(f"{name} cannot contain negative values.")
    return values.astype(np.int64)


def _standings_arrays(standings):
    required = {"team", "points", "goals_for", "goals_against"}
    if not required.issubset(standings.columns):
        raise ValueError(f"Standings require columns: {', '.join(sorted(required))}.")
    teams = standings["team"].tolist()
    if not teams or any(not isinstance(team, str) or not team.strip() for team in teams) or len(set(teams)) != len(teams):
        raise ValueError("Standings must contain unique, nonempty teams.")
    return (
        teams,
        _integers(standings["points"], "points", nonnegative=False),
        _integers(standings["goals_for"], "goals_for"),
        _integers(standings["goals_against"], "goals_against"),
    )


def _played_stats(teams, matches):
    size = len(teams)
    points = np.zeros((size, size), dtype=np.int64)
    goals = np.zeros_like(points)
    away_goals = np.zeros_like(points)
    wins = np.zeros(size, dtype=np.int64)
    away_wins = np.zeros_like(wins)
    if matches is None or matches.empty:
        return points, goals, away_goals, wins, away_wins
    columns = ["homeTeam", "awayTeam", "homeGoals", "awayGoals"]
    if not set(columns).issubset(matches.columns):
        raise ValueError("Played matches require homeTeam, awayTeam, homeGoals, awayGoals.")
    indices = {team: i for i, team in enumerate(teams)}
    scores = _integers(matches[["homeGoals", "awayGoals"]], "played scores")
    for (home, away), (hg, ag) in zip(
        matches[["homeTeam", "awayTeam"]].itertuples(index=False, name=None), scores
    ):
        if home not in indices or away not in indices or home == away:
            raise ValueError("Played matches contain an unknown team or a self fixture.")
        h, a = indices[home], indices[away]
        goals[h, a] += hg
        goals[a, h] += ag
        away_goals[a, h] += ag
        points[h, a] += 3 if hg > ag else int(hg == ag)
        points[a, h] += 3 if ag > hg else int(hg == ag)
        wins[h] += int(hg > ag)
        wins[a] += int(ag > hg)
        away_wins[a] += int(ag > hg)
    return points, goals, away_goals, wins, away_wins


def _groups(indices, values):
    groups = {}
    for i in indices:
        groups.setdefault(values[i], []).append(i)
    return [groups[value] for value in sorted(groups, reverse=True)]


def _rank_indices(points, gf, ga, hp, hg, ha, wins, away_wins, competition, tie):
    gd = gf - ga

    def fixed(group, criteria):
        return sorted(group, key=lambda i: tuple(value[i] for value in criteria) + (tie[i],), reverse=True)

    def head_values(group):
        return hp[:, group].sum(axis=1), (hg - hg.T)[:, group].sum(axis=1)

    def spanish(group):
        if len(group) < 2:
            return group
        h_points, h_gd = head_values(group)
        criteria = [h_gd, gd, gf] if len(group) == 2 else [h_points, h_gd, gd, gf]
        for values in criteria:
            subgroups = _groups(group, values)
            if len(subgroups) > 1:
                # RFEF reapplies the applicable rules to the remaining tied clubs.
                return [i for subgroup in subgroups for i in spanish(subgroup)]
        return fixed(group, [])

    result = []
    for group in _groups(range(len(points)), points):
        if competition == "PD":
            result.extend(spanish(group))
        elif competition == "SA":
            result.extend(fixed(group, [*head_values(group), gd, gf]))
        else:
            primary = [gd] if competition == "FL1" else [gd, gf]
            remaining = [group]
            for criterion in primary:
                remaining = [subgroup for g in remaining for subgroup in _groups(g, criterion)]
            for tied in remaining:
                h_points, h_gd = head_values(tied)
                if competition == "PL":
                    criteria = [h_points, ha[:, tied].sum(axis=1)]
                elif competition == "BL1":
                    criteria = [h_gd, ha[:, tied].sum(axis=1), ha.sum(axis=1)]
                elif competition == "FL1":
                    criteria = [h_points, h_gd, gf, wins, away_wins]
                else:
                    criteria = []
                result.extend(fixed(tied, criteria))
    return np.asarray(result, dtype=int)


def rank_teams(
    teams, points, goals_for, goals_against, *, played_matches=None,
    head_to_head_points=None, head_to_head_goals=None, head_to_head_away_goals=None,
    wins=None, away_wins=None, competition="PD", tie_break=None,
):
    teams = list(teams)
    if not teams or any(not isinstance(team, str) or not team.strip() for team in teams) or len(set(teams)) != len(teams):
        raise ValueError("Ranking requires unique, nonempty teams.")
    size = len(teams)
    points = _integers(points, "points", nonnegative=False)
    gf = _integers(goals_for, "goals_for")
    ga = _integers(goals_against, "goals_against")
    if any(values.shape != (size,) for values in (points, gf, ga)):
        raise ValueError("Ranking arrays must have one value per team.")
    base = _played_stats(teams, played_matches)
    overrides = (head_to_head_points, head_to_head_goals, head_to_head_away_goals, wins, away_wins)
    stats = []
    for i, (default, override) in enumerate(zip(base, overrides)):
        values = default if override is None else _integers(override, "head-to-head/win statistics")
        expected = (size, size) if i < 3 else (size,)
        if values.shape != expected:
            raise ValueError(f"Head-to-head/win statistics must have shape {expected}.")
        stats.append(values)
    # Callers supply seeded random values for unresolved discipline/playoff ties.
    tie = -np.arange(size) if tie_break is None else np.asarray(tie_break, dtype=float)
    if tie.shape != (size,) or not np.isfinite(tie).all():
        raise ValueError("tie_break must have one finite value per team.")
    return _rank_indices(points, gf, ga, *stats, str(competition).upper(), tie)


def rank_table(standings, played_matches=None, competition="PD", tie_break=None):
    teams, points, gf, ga = _standings_arrays(standings)
    order = rank_teams(
        teams, points, gf, ga, played_matches=played_matches,
        competition=competition, tie_break=tie_break,
    )
    return [teams[i] for i in order]


def _fixture_distribution(fixture):
    outcomes = np.asarray([fixture.p_home_win, fixture.p_draw, fixture.p_away_win], dtype=float)
    if not np.isfinite(outcomes).all() or (outcomes < 0).any() or not np.isclose(outcomes.sum(), 1):
        raise ValueError("Fixture outcome probabilities must be finite, nonnegative and sum to 1.")
    scores = _integers(fixture.scorelines, "scorelines")
    if scores.ndim != 2 or scores.shape[1] != 2 or not len(scores):
        raise ValueError("scorelines must have shape (n_scores, 2) and cannot be empty.")
    conditional = np.asarray(fixture.score_probs_by_outcome, dtype=float)
    if conditional.shape != (3, len(scores)) or not np.isfinite(conditional).all() or (conditional < 0).any():
        raise ValueError("Score probabilities must be finite, nonnegative and have shape (3, n_scores).")
    masks = (scores[:, 0] > scores[:, 1], scores[:, 0] == scores[:, 1], scores[:, 0] < scores[:, 1])
    for p, probabilities, mask in zip(outcomes, conditional, masks):
        if p > 0 and (not np.isclose(probabilities.sum(), 1) or (probabilities[~mask] > 0).any()):
            raise ValueError("Conditional score probabilities must sum to 1 and match their outcome.")
    mixture = outcomes @ conditional
    return scores, mixture / mixture.sum()


def simulate_season_scores(
    fixtures, standings, n_sim=3000, seed=None, *, played_matches=None,
    competition="PD", return_details=False,
):
    if isinstance(n_sim, bool) or not isinstance(n_sim, (int, np.integer)) or n_sim <= 0:
        raise ValueError("n_sim must be a positive integer.")
    teams, base_points, base_gf, base_ga = _standings_arrays(standings)
    indices = {team: i for i, team in enumerate(teams)}
    prepared = []
    for fixture in fixtures:
        if fixture.home not in indices or fixture.away not in indices or fixture.home == fixture.away:
            raise ValueError("Fixtures contain an unknown team or a self fixture.")
        scores, probabilities = _fixture_distribution(fixture)
        prepared.append((indices[fixture.home], indices[fixture.away], scores, probabilities))

    rng = np.random.default_rng(seed)
    shape = (n_sim, len(teams))
    points = np.broadcast_to(base_points, shape).copy()
    gf = np.broadcast_to(base_gf, shape).copy()
    ga = np.broadcast_to(base_ga, shape).copy()
    hp, hg, ha, wins, away_wins = [
        np.broadcast_to(values, (n_sim, *values.shape)).copy()
        for values in _played_stats(teams, played_matches)
    ]

    # Sample every simulation together; retain scorelines for league tie-breaks.
    for home, away, scores, probabilities in prepared:
        sample = scores[rng.choice(len(scores), size=n_sim, p=probabilities)]
        home_goals, away_goals = sample[:, 0], sample[:, 1]
        home_win, away_win = home_goals > away_goals, away_goals > home_goals
        draw = home_goals == away_goals
        home_points, away_points = 3 * home_win + draw, 3 * away_win + draw
        points[:, home] += home_points
        points[:, away] += away_points
        gf[:, home] += home_goals
        ga[:, home] += away_goals
        gf[:, away] += away_goals
        ga[:, away] += home_goals
        hp[:, home, away] += home_points
        hp[:, away, home] += away_points
        hg[:, home, away] += home_goals
        hg[:, away, home] += away_goals
        ha[:, away, home] += away_goals
        wins[:, home] += home_win
        wins[:, away] += away_win
        away_wins[:, away] += away_win

    counts = np.zeros((len(teams), len(teams)), dtype=np.int64)
    tie = rng.random(shape)
    positions = np.arange(len(teams))
    for i in range(n_sim):
        order = _rank_indices(
            points[i], gf[i], ga[i], hp[i], hg[i], ha[i], wins[i], away_wins[i],
            str(competition).upper(), tie[i],
        )
        counts[order, positions] += 1
    counts = pd.DataFrame(counts, index=teams, columns=np.arange(1, len(teams) + 1))
    return (counts, points) if return_details else counts


def simulate_season(fixtures, standings, n_sim=5000, seed=None):
    # Compatibility path: probabilities alone imply minimal 1-0, 0-0, 0-1 scores.
    scores = np.array([[1, 0], [0, 0], [0, 1]])
    conditional = tuple(np.eye(3))
    specs = [
        FixtureSimulationSpec(
            row["homeTeam"], row["awayTeam"], row["p_home_win"], row["p_draw"],
            row["p_away_win"], scores, conditional,
        )
        for _, row in fixtures.iterrows()
    ]
    if not {"goals_for", "goals_against"}.issubset(standings.columns):
        standings = standings.copy()
        standings["goals_for"] = standings["goal_diff"].clip(lower=0)
        standings["goals_against"] = -standings["goal_diff"].clip(upper=0)
    return simulate_season_scores(specs, standings, n_sim=n_sim, seed=seed, competition="PL")
