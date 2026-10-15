"""Dated snapshots behind the website's charts and weekly club ranking (`site/data/history/<season>/`).

Three kinds of file, all small and columnar:

- `<competition slug>.json`: each club's title, top-four and relegation chances (Champions League:
  stage chances) through the season, in percent (one decimal below 10, whole numbers above). A point is added on each day that brings new results; a refresh
  without new results updates the latest point instead, so the file grows with match days, not runs.
- `clubs.json`: every rated club's overall, attack and defence ratings, frozen once a week on Monday,
  after the weekend round and the previous week's Champions League games.
- `ratings/<YYYY-MM>.json`: the same ratings plus the five league averages at every refresh with fresh club
  ratings, one month per file by the run's forecast origin, so a match page can compare the last run before
  kickoff with the first run after the result.

The functions here work on plain dicts so the refresh, the backfill and the tests share them.
"""

from __future__ import annotations

import pandas as pd

LEAGUE_METRICS = ("title", "ucl", "releg")
UCL_METRICS = ("top8", "top24", "last16", "qf", "sf", "final", "title")
CLUB_FIELDS = ("rating", "attack", "defense")
# The weekly ranking is frozen at the first refresh of the week, if that comes by Tuesday morning;
# later refreshes would include that week's Champions League games.
FREEZE_DAYS = 2


def _round(value):
    return None if value is None else round(float(value), 1)


def chance(value):
    """A percentage as stored: one decimal below 10, whole above (the site shows whole percentages)."""
    if value is None:
        return None
    value = float(value)
    value = round(value, 1) if value < 10 else float(int(value + 0.5))
    return int(value) if value.is_integer() else value


def competition_values(data):
    """The tracked chances for one competition's site JSON: (metrics, [(team id, name, values)])."""
    if data["kind"] == "ucl":
        rows = [(team, [team["r16"], team["r16"] + team["playoff"], team["stages"]["round16"],
                        team["stages"]["quarterfinal"], team["stages"]["semifinal"], team["stages"]["final"],
                        team["title"]]) for team in data["teams"]]
        metrics = UCL_METRICS
    else:
        rows = [(team, [team["title"], team["ucl"], team["releg"]]) for team in data["teams"]]
        metrics = LEAGUE_METRICS
    return metrics, [(team_key(team), team["name"], [chance(value) for value in values]) for team, values in rows]


def team_key(team):
    """football-data.org's team id, or the slug for the rare club without one."""
    return team["id"] if team.get("id") is not None else team["slug"]


def season_key(season):
    """`2026/27` -> `2026`, the folder a season's history lives in."""
    return str(season).split("/")[0]


def add_point(history, data, date):
    """Add one competition forecast (its site JSON) as the point for `date` (YYYY-MM-DD, UTC).

    The point replaces the latest one when it falls on the same day or brings no new results
    (same `data_cutoff`); the replaced point keeps its date. Dates before the latest point are
    refused, so a refresh cannot rewrite the past; `merge_points` combines a backfill with it.
    """
    metrics, rows = competition_values(data)
    if not history or history.get("season") != data["season"] or tuple(history.get("metrics", ())) != metrics:
        history = {"slug": data["slug"], "season": data["season"], "metrics": list(metrics), "dates": [],
                   "cutoff": None, "teams": []}
    dates = history["dates"]
    if dates and date < dates[-1]:
        raise ValueError(f"{data['slug']}: {date} precedes the latest point ({dates[-1]}).")
    cutoff = data.get("data_cutoff")
    if not dates or (date != dates[-1] and cutoff != history["cutoff"]):
        dates.append(date)
    at = len(dates) - 1
    teams = {team["id"]: team for team in history["teams"]}
    for team_id, name, values in rows:
        if team_id not in teams:
            teams[team_id] = {"id": team_id, "name": name, **{metric: [] for metric in metrics}}
            history["teams"].append(teams[team_id])
        teams[team_id]["name"] = name
        for metric, value in zip(metrics, values):
            teams[team_id][metric] = _pad(teams[team_id][metric], len(dates))
            teams[team_id][metric][at] = value
    for team in history["teams"]:
        for metric in metrics:
            team[metric] = _pad(team[metric], len(dates))
    history["cutoff"] = cutoff
    return history


def _pad(series, length):
    return (series + [None] * (length - len(series)))[:length]


def points(history):
    """The history as a list of {date, values: {team id: [values]}}, plus team names."""
    names = {team["id"]: team["name"] for team in history["teams"]}
    out = []
    for i, date in enumerate(history["dates"]):
        values = {team["id"]: [team[metric][i] for metric in history["metrics"]] for team in history["teams"]}
        out.append({"date": date, "values": {key: row for key, row in values.items() if any(v is not None for v in row)}})
    return out, names


def merge_points(earlier, later):
    """A backfilled history followed by the points of `later` dated after it (same season and metrics)."""
    if not later or later.get("season") != earlier["season"] or later["metrics"] != earlier["metrics"]:
        return earlier
    first, names = points(earlier)
    second, later_names = points(later)
    last = first[-1]["date"] if first else ""
    combined = first + [point for point in second if point["date"] > last]
    names = {**names, **later_names}
    ids = list(dict.fromkeys([team["id"] for team in earlier["teams"]] + [team["id"] for team in later["teams"]]))
    merged = {**earlier, "dates": [point["date"] for point in combined],
              "cutoff": later["cutoff"] if len(combined) > len(first) else earlier["cutoff"], "teams": []}
    for team_id in ids:
        team = {"id": team_id, "name": names[team_id]}
        for m, metric in enumerate(earlier["metrics"]):
            team[metric] = [point["values"].get(team_id, [None] * len(earlier["metrics"]))[m] for point in combined]
        merged["teams"].append(team)
    return merged


def week_of(as_of):
    """The Monday (YYYY-MM-DD) starting the UTC week of `as_of`, and whether it can still be frozen."""
    as_of = pd.to_datetime(as_of, utc=True)
    monday = (as_of.normalize() - pd.Timedelta(days=as_of.weekday())).date().isoformat()
    return monday, as_of.weekday() < FREEZE_DAYS


def freeze_week(history, ratings, *, as_of, season, cutoff=None):
    """Record `ratings` ({club id: (rating, attack, defense)}) as the week's ranking, once per week.

    Only the first refresh of a week, by Tuesday morning, freezes it; returns the history and
    whether a week was added.
    """
    monday, open_ = week_of(as_of)
    if not history or history.get("season") != season:
        history = {"season": season, "fields": list(CLUB_FIELDS), "weeks": []}
    weeks = history["weeks"]
    if not open_ or not ratings or any(week["date"] >= monday for week in weeks):
        return history, False
    weeks.append({"date": monday, "cutoff": cutoff,
                  "clubs": {str(club): [_round(value) for value in values] for club, values in ratings.items()}})
    return history, True


def merge_weeks(earlier, later):
    """Backfilled weeks followed by the weeks of `later` dated after them (same season)."""
    if not later or later.get("season") != earlier["season"]:
        return earlier
    last = earlier["weeks"][-1]["date"] if earlier["weeks"] else ""
    return {**earlier, "weeks": earlier["weeks"] + [week for week in later["weeks"] if week["date"] > last]}


def run_month(as_of):
    """`2026-10-14T18:40:00+00:00` -> `2026-10`, the UTC month whose file holds that run."""
    return pd.to_datetime(as_of, utc=True).strftime("%Y-%m")


def add_run(history, ratings, *, as_of, season, cutoff=None, leagues=None):
    """Append one refresh's `ratings` ({club id: (rating, attack, defense)}) and league averages to its month.

    Runs are append-only: a run at or before the month's latest origin is refused (returns False), so a
    rerun of the same outputs adds nothing and a refresh cannot rewrite earlier runs.
    """
    month = run_month(as_of)
    if not history or history.get("season") != season or history.get("month") != month:
        history = {"season": season, "month": month, "fields": list(CLUB_FIELDS), "runs": []}
    runs = history["runs"]
    if not ratings or (runs and pd.Timestamp(runs[-1]["as_of"]) >= pd.Timestamp(as_of)):
        return history, False
    runs.append({"as_of": as_of, "cutoff": cutoff, "leagues": dict(leagues or {}),
                 "clubs": {str(club): [_round(value) for value in values] for club, values in ratings.items()}})
    return history, True
