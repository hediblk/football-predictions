from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import skellam

from standing_prediction.defaults import CALIBRATION_VERSION, DEFAULT_WEIGHTS
from standing_prediction.ensemble import blend_probabilities
from standing_prediction.odds import match_odds


STAGES = {
    "LEAGUE_STAGE": "league", "LEAGUE_PHASE": "league",
    "PLAYOFFS": "playoffs", "KNOCKOUT_ROUND_PLAY_OFFS": "playoffs",
    "LAST_16": "round16", "ROUND_OF_16": "round16",
    "QUARTER_FINALS": "quarterfinal", "SEMI_FINALS": "semifinal", "FINAL": "final",
}


@dataclass
class TournamentResult:
    probabilities: pd.DataFrame
    summary: pd.DataFrame
    bracket: dict
    metadata: dict
    league_orders: np.ndarray
    league_points: np.ndarray


def _stage(value):
    return STAGES.get(str(value).upper(), str(value).lower())


def _neutral(row, final=False):
    value = row.get("neutral", False) if row is not None else False
    return final or (not pd.isna(value) and bool(value))


def _score(row):
    if row.get("status") not in {"FINISHED", "AWARDED"}:
        return None
    values = [row.get("homeGoals"), row.get("awayGoals")]
    if any(pd.isna(value) for value in values):
        raise ValueError(f"Finished fixture {row.get('id')} lacks a 90-minute score.")
    if any(not np.isfinite(value) or value < 0 or value != int(value) for value in values):
        raise ValueError("Match scores must be finite nonnegative integers.")
    return tuple(int(value) for value in values)


def _league_fixtures(fixtures):
    if "stage" not in fixtures:
        raise ValueError("UCL fixtures require their competition stage.")
    return fixtures.loc[fixtures["stage"].map(_stage).eq("league")].copy()


def validate_league_phase(fixtures, standings):
    required = {"team", "position", "played", "points", "goals_for", "goals_against"}
    if not required.issubset(standings):
        raise ValueError(f"UCL standings require {sorted(required)}.")
    teams = standings["team"].tolist()
    if len(teams) != 36 or len(set(teams)) != 36:
        raise ValueError("The Champions League league phase requires 36 unique clubs.")
    league = _league_fixtures(fixtures)
    if len(league) != 144:
        raise ValueError(f"Expected 144 league-phase fixtures; received {len(league)}.")
    if not {"homeTeam", "awayTeam", "homeGoals", "awayGoals", "status"}.issubset(league):
        raise ValueError("UCL fixtures lack clubs, statuses or regular-time score columns.")
    if "id" in league and league["id"].notna().all() and league["id"].duplicated().any():
        raise ValueError("Duplicate UCL league-phase match IDs.")
    if league[["homeTeam", "awayTeam"]].duplicated().any():
        raise ValueError("Duplicate UCL league-phase fixture.")
    known = set(teams)
    opponents = {team: set() for team in teams}
    home_counts, away_counts = dict.fromkeys(teams, 0), dict.fromkeys(teams, 0)
    totals = {team: np.zeros(4, dtype=int) for team in teams}
    finished = 0
    for row in league.to_dict("records"):
        home, away = row["homeTeam"], row["awayTeam"]
        if home not in known or away not in known or home == away:
            raise ValueError("Unknown club or self fixture in UCL league phase.")
        opponents[home].add(away)
        opponents[away].add(home)
        home_counts[home] += 1
        away_counts[away] += 1
        score = _score(row)
        if score is not None:
            hg, ag = score
            totals[home] += [1, 3 * (hg > ag) + (hg == ag), hg, ag]
            totals[away] += [1, 3 * (ag > hg) + (hg == ag), ag, hg]
            finished += 1
    if any(len(opponents[t]) != 8 or home_counts[t] != 4 or away_counts[t] != 4 for t in teams):
        raise ValueError("Each UCL club must have eight distinct opponents and four home/four away matches.")
    table = standings.set_index("team")
    for team in teams:
        official = table.loc[team, ["played", "points", "goals_for", "goals_against"]].to_numpy(dtype=float)
        if not np.isfinite(official).all() or not np.array_equal(official, totals[team]):
            raise ValueError(f"Played UCL scores disagree with official standings for {team}.")
    positions = standings["position"].to_numpy(dtype=float)
    if finished == 144 and sorted(positions) != list(range(1, 37)):
        raise ValueError("Completed league phase requires official final positions 1–36.")
    return {"clubs": 36, "fixtures": 144, "finished": finished, "remaining": 144 - finished,
            "official_final_ranks": finished == 144}


def rank_league_phase(teams, points, goals_for, goals_against, away_goals, wins,
                      away_wins, opponents, *, tie_break=None, coefficients=None):
    values = [np.asarray(x) for x in (points, goals_for, goals_against, away_goals, wins, away_wins)]
    if any(x.shape != values[0].shape for x in values) or values[0].shape[-1] != len(teams):
        raise ValueError("League ranking statistics must have one column per club.")
    if any(not np.isfinite(x).all() for x in values):
        raise ValueError("League ranking statistics must be finite.")
    points, gf, ga, away_goals, wins, away_wins = values
    opponents = np.asarray(opponents)
    if opponents.shape != (len(teams), len(teams)):
        raise ValueError("Opponents must be the club-by-club league-schedule adjacency matrix.")
    tie = np.zeros_like(points, dtype=float) if tie_break is None else np.asarray(tie_break)
    if tie.shape != points.shape or not np.isfinite(tie).all():
        raise ValueError("Ranking tie-break values must match the points array.")
    coefficient = np.asarray([float((coefficients or {}).get(t, 0)) for t in teams])
    coefficient = np.broadcast_to(coefficient, points.shape)
    return np.lexsort((-coefficient, -tie, -(gf @ opponents), -((gf - ga) @ opponents),
                       -(points @ opponents), -away_wins, -wins, -away_goals,
                       -gf, -(gf - ga), -points), axis=-1)


class MatchupCache:
    def __init__(self, teams, model, max_goals=10):
        self.teams, self.model, self.max_goals = list(teams), model, max_goals
        self.indices = {team: i for i, team in enumerate(teams)}
        self.goals = np.arange(max_goals + 1)
        self.width = len(self.goals)
        self.scores = np.stack(np.meshgrid(self.goals, self.goals, indexing="ij"), axis=-1).reshape(-1, 2)
        self.outcome_masks = (self.scores[:, 0] > self.scores[:, 1], self.scores[:, 0] == self.scores[:, 1],
                              self.scores[:, 0] < self.scores[:, 1])
        shape = (len(teams), len(teams), 2)
        self.probabilities = np.zeros((*shape, self.width ** 2))
        self.rates = np.zeros((*shape, 2))
        for home, h in self.indices.items():
            for away, a in self.indices.items():
                if h == a:
                    continue
                for neutral in (False, True):
                    goals, matrix = model.score_matrix(home, away, max_goals=max_goals, neutral=neutral)
                    if not np.array_equal(goals, self.goals):
                        raise ValueError("The model score matrix uses unexpected goal support.")
                    self.probabilities[h, a, int(neutral)] = self._blend(matrix, model.elo_probs(home, away, neutral=neutral))
                    self.rates[h, a, int(neutral)] = model.expected_goals(home, away, neutral=neutral)
        self.cdf = self.probabilities.cumsum(axis=-1)
        self.cdf[..., -1] = 1

    def _blend(self, matrix, elo, odds=None):
        p = np.asarray(matrix, dtype=float).ravel().copy()
        if not np.isfinite(p).all() or (p < 0).any() or p.sum() <= 0:
            raise ValueError("Invalid model score probabilities.")
        p /= p.sum()
        outcomes = [p[mask].sum() for mask in self.outcome_masks]
        blend = blend_probabilities(outcomes, p_elo=elo, p_odds=odds, weights=DEFAULT_WEIGHTS)
        for mask, old, new in zip(self.outcome_masks, outcomes, blend):
            if old > 0:
                p[mask] *= new / old
        return p / p.sum()

    def distribution(self, home, away, *, neutral=False, odds=None):
        h = self.indices[home] if isinstance(home, str) else home
        a = self.indices[away] if isinstance(away, str) else away
        if odds is None:
            return self.probabilities[h, a, int(neutral)]
        _, matrix = self.model.score_matrix(self.teams[h], self.teams[a], max_goals=self.max_goals, neutral=neutral)
        return self._blend(matrix, self.model.elo_probs(self.teams[h], self.teams[a], neutral=neutral), odds)

    def sample(self, home, away, rng, *, neutral=False):
        home, away = np.asarray(home), np.asarray(away)
        u = rng.random(home.shape)
        choice = (u[..., None] > self.cdf[home, away, np.asarray(neutral, dtype=int)]).sum(axis=-1)
        return choice // self.width, choice % self.width

    def difference(self, home, away, *, neutral=False, odds=None):
        p = self.distribution(home, away, neutral=neutral, odds=odds)
        return np.bincount(self.scores[:, 0] - self.scores[:, 1] + self.max_goals,
                           weights=p, minlength=2 * self.max_goals + 1)

    def tie_probability(self, team1, team2, *, home_second_leg=None, final=False, rows=None, quotes=None):
        rows, quotes = rows or [], quotes or {}
        known = _observed_winner(rows, team1, team2, final=final)
        if known is not None:
            return float(known == team1)
        home_second_leg = _second_home(rows, team1, team2, home_second_leg)
        legs = [(rows[0]["homeTeam"], rows[0]["awayTeam"]) if rows else (team1, team2)] if final else [(team2 if home_second_leg == team1 else team1,
                                               home_second_leg), (home_second_leg,
                                               team2 if home_second_leg == team1 else team1)]
        mass, origin = np.array([1.]), 0
        for home, away in legs:
            row = next((r for r in rows if r["homeTeam"] == home and r["awayTeam"] == away), None)
            score = _score(row) if row is not None else None
            if score is not None:
                origin += (score[0] - score[1]) * (1 if home == team1 else -1)
            else:
                probabilities = self.difference(home, away, neutral=_neutral(row, final), odds=quotes.get(_fixture_key(row)))
                mass = np.convolve(mass, probabilities if home == team1 else probabilities[::-1])
                origin -= self.max_goals
        differences = np.arange(len(mass)) + origin
        h, a = legs[-1]
        last = next((r for r in rows if r["homeTeam"] == h and r["awayTeam"] == a), None)
        rates = self.rates[self.indices[h], self.indices[a], int(_neutral(last, final))] / 3
        et_home = float(skellam.sf(0, *rates) + .5 * skellam.pmf(0, *rates))
        et_team1 = et_home if h == team1 else 1 - et_home
        return float(mass[differences > 0].sum() + mass[differences == 0].sum() * et_team1)


def _fixture_key(row):
    if row is None:
        return None
    return (row.get("id"), row.get("homeTeam"), row.get("awayTeam"), str(row.get("utcDate")))


def _period(row, period):
    value = row.get(period)
    if not isinstance(value, dict):
        score = row.get("score")
        value = score.get(period) if isinstance(score, dict) else None
    if isinstance(value, dict) and all(value.get(side) is not None for side in ("home", "away")):
        return int(value["home"]), int(value["away"])
    return None


def _observed_winner(rows, team1, team2, *, final=False):
    needed = 1 if final else 2
    if len(rows) < needed or any(_score(row) is None for row in rows):
        return None
    if len(rows) != needed:
        raise ValueError("Unexpected number of fixtures for a knockout tie.")
    difference = sum((_score(r)[0] - _score(r)[1]) * (1 if r["homeTeam"] == team1 else -1) for r in rows)
    if difference:
        return team1 if difference > 0 else team2
    last = rows[-1]
    for period in ("extraTime", "penalties"):
        score = _period(last, period)
        if score is not None and score[0] != score[1]:
            return last["homeTeam"] if score[0] > score[1] else last["awayTeam"]
    score = last.get("score")
    winner = last.get("winner") or (score.get("winner") if isinstance(score, dict) else None)
    if winner in {"HOME_TEAM", "AWAY_TEAM"}:
        return last["homeTeam"] if winner == "HOME_TEAM" else last["awayTeam"]
    raise ValueError("A completed level knockout tie lacks extra-time/shootout winner data.")


def _second_home(rows, team1, team2, default):
    if len(rows) >= 2:
        return rows[-1]["homeTeam"]
    if rows:
        return team2 if rows[0]["homeTeam"] == team1 else team1
    return default or team1


def _knockout_rows(fixtures):
    observed = {}
    for row in fixtures.sort_values("utcDate").to_dict("records"):
        stage = _stage(row["stage"])
        if stage in {"playoffs", "round16", "quarterfinal", "semifinal", "final"}:
            key = (stage, frozenset((row["homeTeam"], row["awayTeam"])))
            observed.setdefault(key, []).append(row)
    return observed


def _draw(order, bits):
    order, bits = np.atleast_2d(order), np.atleast_2d(bits)
    order = np.broadcast_to(order, (len(bits), 36))
    seeded, unseeded, direct = [], [], []
    # Annex B: silver half followed by blue half, from top to bottom.
    for group, (seed, unseed, top) in enumerate(((10, 20, 4), (12, 18, 2), (8, 22, 6), (14, 16, 0))):
        row = np.arange(len(bits))
        seeded.append(np.stack((order[row, seed + bits[:, group]], order[row, seed + 1 - bits[:, group]]), axis=1))
        unseeded.append(np.stack((order[row, unseed + bits[:, group + 4]], order[row, unseed + 1 - bits[:, group + 4]]), axis=1))
        direct.append(np.stack((order[row, top + bits[:, group + 8]], order[row, top + 1 - bits[:, group + 8]]), axis=1))
    return tuple(np.stack(values, axis=1).transpose(0, 2, 1).reshape(len(bits), 8)
                 for values in (seeded, unseeded, direct))


def _draws(orders, rng, observed, teams):
    if not observed:
        return _draw(orders, rng.integers(0, 2, (len(orders), 12)))
    if not (orders == orders[0]).all():
        raise ValueError("Published knockout fixtures require completed official league ranks.")
    bits = ((np.arange(4096)[:, None] >> np.arange(12)) & 1)
    seeded, unseeded, direct = _draw(orders[:1], bits)
    slots = np.full((4096, 36), -1, dtype=int)
    row = np.arange(4096)[:, None]
    for values in (seeded, unseeded, direct):
        slots[row, values] = np.arange(8)
    indices = {team: i for i, team in enumerate(teams)}
    valid = np.ones(4096, dtype=bool)
    for (stage, pair), rows in observed.items():
        if len(pair) != 2 or any(team not in indices for team in pair):
            raise ValueError("Invalid club in published knockout fixture.")
        first, second = [indices[t] for t in pair]
        x, y = slots[:, first], slots[:, second]
        condition = (x >= 0) & (y >= 0)
        if stage == "playoffs":
            condition &= (((seeded == first) & (unseeded == second)) | ((seeded == second) & (unseeded == first))).any(axis=1)
        elif stage == "round16":
            condition &= (x == y) & ((direct == first).any(axis=1) | (direct == second).any(axis=1))
        elif stage == "quarterfinal":
            condition &= (x // 2 == y // 2) & (x != y)
        elif stage == "semifinal":
            condition &= (x // 4 == y // 4) & (x // 2 != y // 2)
        else:
            condition &= x // 4 != y // 4
        valid &= condition
    choices = np.flatnonzero(valid)
    if not len(choices):
        raise ValueError("Published knockout fixtures conflict with the permitted UEFA bracket paths.")
    sample = rng.choice(choices, size=len(orders))
    return seeded[sample], unseeded[sample], direct[sample]


def _play_ties(team1, team2, second_home, stage, cache, observed, quotes, rng):
    team1, team2, second_home = np.asarray(team1), np.asarray(team2), np.asarray(second_home).copy()
    final = stage == "final"
    relevant = []
    for (known_stage, pair), rows in observed.items():
        if known_stage != stage:
            continue
        a, b = [cache.indices[t] for t in pair]
        mask = ((team1 == a) & (team2 == b)) | ((team1 == b) & (team2 == a))
        if not mask.any():
            continue
        if not final:
            actual_second = _second_home(rows, cache.teams[a], cache.teams[b], cache.teams[a])
            second_home[mask] = cache.indices[actual_second]
        relevant.append((mask, rows))
    other = np.where(second_home == team1, team2, team1)
    if final:
        home, away = team1.copy(), team2.copy()
        for mask, rows in relevant:
            home[mask], away[mask] = cache.indices[rows[0]["homeTeam"]], cache.indices[rows[0]["awayTeam"]]
        legs = [(home, away)]
    else:
        legs = [(other, second_home), (second_home, other)]
    difference = np.zeros(team1.shape, dtype=int)
    for home, away in legs:
        neutral = np.full(home.shape, final, dtype=bool)
        for mask, rows in relevant:
            for row in rows:
                row_mask = mask & (home == cache.indices[row["homeTeam"]]) & (away == cache.indices[row["awayTeam"]])
                neutral[row_mask] = _neutral(row, final)
        hg, ag = cache.sample(home, away, rng, neutral=neutral)
        for mask, rows in relevant:
            for row in rows:
                row_mask = mask & (home == cache.indices[row["homeTeam"]]) & (away == cache.indices[row["awayTeam"]])
                if not row_mask.any():
                    continue
                score = _score(row)
                if score is not None:
                    hg[row_mask], ag[row_mask] = score
                elif _fixture_key(row) in quotes:
                    p = cache.distribution(row["homeTeam"], row["awayTeam"], neutral=_neutral(row, final), odds=quotes[_fixture_key(row)])
                    sample = rng.choice(len(p), row_mask.sum(), p=p)
                    hg[row_mask], ag[row_mask] = sample // cache.width, sample % cache.width
        difference += (hg - ag) * np.where(home == team1, 1, -1)
    level = difference == 0
    if level.any():
        home, away = legs[-1]
        rates = cache.rates[home[level], away[level], neutral[level].astype(int)] / 3
        et = rng.poisson(rates)
        delta = (et[:, 0] - et[:, 1]) * np.where(home[level] == team1[level], 1, -1)
        delta[delta == 0] = rng.choice([-1, 1], (delta == 0).sum())
        difference[level] = delta
    winners = np.where(difference > 0, team1, team2)
    for mask, rows in relevant:
        first, second = [cache.teams[int(t)] for t in (team1[mask][0], team2[mask][0])]
        known = _observed_winner(rows, first, second, final=final)
        if known is not None:
            winners[mask] = cache.indices[known]
    return winners, second_home


def _representative(order, cache, observed, quotes, seed, season, title_favorite):
    rng = np.random.default_rng(seed)
    seeded, unseeded, direct = [values[0] for values in _draws(order[None, :], rng, observed, cache.teams)]
    stages = {}

    def round_ties(stage, a, b, homes):
        ties, winners = [], []
        for slot, (t1, t2, home) in enumerate(zip(a, b, homes)):
            name1, name2 = cache.teams[t1], cache.teams[t2]
            rows = observed.get((stage, frozenset((name1, name2))), [])
            home_name = _second_home(rows, name1, name2, cache.teams[home])
            probability = cache.tie_probability(name1, name2, home_second_leg=home_name,
                                                final=stage == "final", rows=rows, quotes=quotes)
            winner = t1 if probability >= .5 else t2
            ties.append({"slot": slot, "team1": name1, "team2": name2,
                         "winner": cache.teams[winner], "advance_probability": 100 * max(probability, 1 - probability),
                         "home_second_leg": None if stage == "final" else home_name,
                         "observed": _observed_winner(rows, name1, name2, final=stage == "final") is not None})
            winners.append(winner)
        stages[stage] = ties
        return np.asarray(winners)

    playoffs = round_ties("playoffs", seeded, unseeded, seeded)
    round16 = round_ties("round16", direct, playoffs, direct)
    qf_homes = round16[1::2] if season >= 2025 else np.where(rng.integers(0, 2, 4), round16[::2], round16[1::2])
    quarterfinal = round_ties("quarterfinal", round16[::2], round16[1::2], qf_homes)
    sf_homes = quarterfinal[1::2] if season >= 2025 else np.where(rng.integers(0, 2, 2), quarterfinal[::2], quarterfinal[1::2])
    semifinal = round_ties("semifinal", quarterfinal[::2], quarterfinal[1::2], sf_homes)
    champion = round_ties("final", semifinal[:1], semifinal[1:], semifinal[:1])
    return {"stages": stages, "champion": cache.teams[champion[0]], "overall_title_favorite": title_favorite,
            "draw_label": "Illustrative permitted draw and match favorites; future pairings are hypothetical"
                          if not observed else "Published pairings with remaining permitted draw slots projected",
            "projected_league_order": [cache.teams[t] for t in order]}


def simulate_tournament(fixtures, standings, model, *, n_sim=10000, seed=7, season=2026,
                        coefficients=None, odds=None, as_of=None):
    if isinstance(n_sim, bool) or not isinstance(n_sim, (int, np.integer)) or n_sim <= 0:
        raise ValueError("n_sim must be a positive integer.")
    fixtures = fixtures.copy()
    fixtures["utcDate"] = pd.to_datetime(fixtures["utcDate"], utc=True)
    cutoff = pd.Timestamp.now(tz="UTC") if as_of is None else pd.to_datetime(as_of, utc=True)
    future = fixtures["utcDate"].ge(cutoff)
    fixtures.loc[future, ["homeGoals", "awayGoals"]] = np.nan
    fixtures.loc[future, "status"] = "SCHEDULED"
    validation = validate_league_phase(fixtures, standings)
    league = _league_fixtures(fixtures)
    teams = standings["team"].tolist()
    cache = MatchupCache(teams, model)
    rng = np.random.default_rng(seed)
    size = len(teams)
    stats = [np.zeros((n_sim, size), dtype=np.int64) for _ in range(6)]
    points, gf, ga, away_goals, wins, away_wins = stats
    opponents = np.zeros((size, size), dtype=int)
    quotes = {}
    if odds is not None and not odds.empty and "observed_at" in odds:
        odds = odds.copy()
        odds["observed_at"] = pd.to_datetime(odds["observed_at"], errors="coerce", utc=True)
        odds = odds.loc[odds["observed_at"].ge(cutoff - pd.Timedelta(days=7))]
        for row in fixtures.to_dict("records"):
            if _score(row) is None:
                match = match_odds(pd.DataFrame([row]), odds, as_of=cutoff)
                if match:
                    quotes[_fixture_key(row)] = match[(row["homeTeam"], row["awayTeam"])]
    for row in league.to_dict("records"):
        h, a = cache.indices[row["homeTeam"]], cache.indices[row["awayTeam"]]
        opponents[h, a] = opponents[a, h] = 1
        score = _score(row)
        if score is None:
            p = cache.distribution(h, a, neutral=_neutral(row), odds=quotes.get(_fixture_key(row)))
            sample = rng.choice(len(p), size=n_sim, p=p)
            hg, ag = sample // cache.width, sample % cache.width
        else:
            hg, ag = [np.full(n_sim, value, dtype=int) for value in score]
        hw, aw, draw = hg > ag, ag > hg, hg == ag
        points[:, h] += 3 * hw + draw
        points[:, a] += 3 * aw + draw
        gf[:, h] += hg
        ga[:, h] += ag
        gf[:, a] += ag
        ga[:, a] += hg
        away_goals[:, a] += ag
        wins[:, h] += hw
        wins[:, a] += aw
        away_wins[:, a] += aw
    fallback = 0
    if validation["official_final_ranks"]:
        order = np.argsort(standings["position"].to_numpy())
        orders = np.broadcast_to(order, (n_sim, size)).copy()
    else:
        orders = rank_league_phase(teams, *stats, opponents, tie_break=rng.random(points.shape), coefficients=coefficients)
        criteria = [points, gf - ga, gf, away_goals, wins, away_wins, points @ opponents,
                    (gf - ga) @ opponents, gf @ opponents]
        tied = np.ones((n_sim, size - 1), dtype=bool)
        for criterion in criteria:
            ranked = np.take_along_axis(criterion, orders, axis=1)
            tied &= ranked[:, :-1] == ranked[:, 1:]
        fallback = int(tied.any(axis=1).sum())
    counts = np.zeros((size, size), dtype=int)
    for position in range(size):
        counts[:, position] = np.bincount(orders[:, position], minlength=size)
    probabilities = pd.DataFrame(counts * (100 / n_sim), index=teams, columns=range(1, size + 1))
    summary = pd.DataFrame(index=pd.Index(teams, name="team"))
    summary["expected_position"] = probabilities.to_numpy() @ np.arange(1, size + 1) / 100
    summary["expected_points"] = points.mean(axis=0)
    summary["points_p10"], summary["points_p90"] = np.percentile(points, [10, 90], axis=0)
    for name, sl in (("top8", slice(0, 8)), ("playoffs", slice(8, 24)), ("eliminated", slice(24, 36))):
        summary[f"{name}_pct"] = np.bincount(orders[:, sl].ravel(), minlength=size) * (100 / n_sim)
    observed = _knockout_rows(fixtures)
    seeded, unseeded, direct = _draws(orders, rng, observed, teams)
    playoff_winners, _ = _play_ties(seeded, unseeded, seeded, "playoffs", cache, observed, quotes, rng)
    summary["round16_pct"] = np.bincount(np.concatenate((direct.ravel(), playoff_winners.ravel())), minlength=size) * (100 / n_sim)
    winners, _ = _play_ties(direct, playoff_winners, direct, "round16", cache, observed, quotes, rng)
    for stage, column in (("quarterfinal", "quarterfinal_pct"), ("semifinal", "semifinal_pct"), ("final", "final_pct")):
        summary[column] = np.bincount(winners.ravel(), minlength=size) * (100 / n_sim)
        first, second = winners[:, ::2], winners[:, 1::2]
        homes = second if season >= 2025 or stage == "final" else np.where(rng.integers(0, 2, first.shape), first, second)
        winners, _ = _play_ties(first, second, homes, stage, cache, observed, quotes, rng)
    summary["title_pct"] = np.bincount(winners.ravel(), minlength=size) * (100 / n_sim)
    for column in list(summary.filter(like="_pct")):
        probability = summary[column] / 100
        summary[column.replace("_pct", "_mc_se")] = 100 * np.sqrt(probability * (1 - probability) / n_sim)
    title_favorite = summary["title_pct"].idxmax()
    projected = np.argsort(summary["expected_position"].to_numpy(), kind="stable")
    bracket = _representative(projected, cache, observed, quotes, seed, season, title_favorite)
    expected_totals = {"top8_pct": 800, "playoffs_pct": 1600, "eliminated_pct": 1200,
                       "round16_pct": 1600, "quarterfinal_pct": 800, "semifinal_pct": 400,
                       "final_pct": 200, "title_pct": 100}
    conservation = {key: {"actual": float(summary[key].sum()), "expected": value}
                    for key, value in expected_totals.items()}
    if any(not np.isclose(value["actual"], value["expected"]) for value in conservation.values()):
        raise RuntimeError("Tournament stage probability conservation failed.")
    metadata = {"season": season, "n_sim": int(n_sim), "seed": seed, "as_of": cutoff.isoformat(),
                "league_validation": validation, "rules_version": f"UEFA-{season}/{str(season + 1)[-2:]}",
                "calibration_version": CALIBRATION_VERSION, "blend_weights": DEFAULT_WEIGHTS,
                "disciplinary_fallback_simulations": fallback,
                "disciplinary_fallback_pct": 100 * fallback / n_sim,
                "coefficients_available": coefficients is not None,
                "quoted_fixtures": len(quotes), "odds_max_age_days": 7, "team_order": teams,
                "score_support_max_goals": cache.max_goals,
                "conservation": conservation,
                "approximations": ["Future disciplinary ties use a seeded random decision before club coefficients.",
                                   "Extra-time rates are one third of 90-minute rates; shootouts are 50/50.",
                                   "Final venue is neutral; aggregate-score tactical changes are not modeled.",
                                   "Future draws sample only permitted UEFA slots; official fixtures fix published pairings and venues.",
                                   "Probabilities condition on fitted strengths; Monte Carlo errors exclude model uncertainty."]}
    probabilities.index.name = "team"
    return TournamentResult(probabilities, summary.sort_values("expected_position"), bracket,
                            metadata, orders, points)
