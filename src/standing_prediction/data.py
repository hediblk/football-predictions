from __future__ import annotations

import json
import os
import warnings

import numpy as np
import pandas as pd
import requests

from standing_prediction.simulate import rank_table
from standing_prediction.utils import cache_max_age, cached_get, normalize_team

BASE_URL = "https://api.football-data.org/v4"
MATCH_COLUMNS = ["id", "utcDate", "matchday", "status", "homeTeam", "awayTeam", "homeTeamId", "awayTeamId", "homeGoals", "awayGoals"]
STANDING_COLUMNS = ["position", "team", "played", "points", "goals_for", "goals_against", "goal_diff"]
# A result counts from kickoff plus three hours, as in the Champions League inputs.
RESULT_DELAY = pd.Timedelta(hours=3)


class FootballDataClient:
    def __init__(self, cache_dir=".cache/football-data", use_cache=True, max_age=None):
        """`max_age` (seconds) overrides the default cache lifetime: an hour for the current season."""
        self.api_key = os.getenv("FOOTBALL_DATA_API_KEY")
        if not self.api_key:
            raise ValueError("FOOTBALL_DATA_API_KEY is not set.")
        self.session = requests.Session()
        self.session.headers.update({"X-Auth-Token": self.api_key})
        self.cache_dir = cache_dir if use_cache else None
        self.max_age = max_age

    def get(self, path, params=None):
        default = cache_max_age((params or {}).get("season"))
        content = cached_get(
            f"{BASE_URL}{path}", params=params, session=self.session, cache_dir=self.cache_dir,
            max_age=default if self.max_age is None or default is None else self.max_age,
        )
        return json.loads(content)


def fetch_standings(client, competition="PD", season=None):
    params = {"season": season} if season is not None else None
    data = client.get(f"/competitions/{competition}/standings", params=params)
    tables = data["standings"]
    table = next((s["table"] for s in tables if s.get("type") == "TOTAL"), tables[0]["table"])
    rows = []
    for row in table:
        rows.append({
            "position": row["position"], "team": row["team"]["name"],
            "played": row["playedGames"], "points": row["points"],
            "goals_for": row["goalsFor"], "goals_against": row["goalsAgainst"],
            "goal_diff": row["goalDifference"],
        })
    return pd.DataFrame(rows, columns=STANDING_COLUMNS)


def fetch_matches(client, competition="PD", season=None, status="FINISHED"):
    params = {}
    if status is not None:
        params["status"] = status
    if season is not None:
        params["season"] = season
    data = client.get(f"/competitions/{competition}/matches", params=params)
    return _matches_to_df(data["matches"])


def _matches_to_df(matches):
    rows = []
    for match in matches:
        full_time = match.get("score", {}).get("fullTime", {})
        rows.append({
            "id": match.get("id"), "utcDate": match.get("utcDate"),
            "matchday": match.get("matchday"), "status": match.get("status"),
            "homeTeam": match["homeTeam"]["name"], "awayTeam": match["awayTeam"]["name"],
            "homeTeamId": match["homeTeam"].get("id"), "awayTeamId": match["awayTeam"].get("id"),
            "homeGoals": full_time.get("home"), "awayGoals": full_time.get("away"),
        })
    df = pd.DataFrame(rows, columns=MATCH_COLUMNS)
    df["utcDate"] = pd.to_datetime(df["utcDate"], errors="coerce", utc=True)
    return df


OVERRIDE_COLUMNS = ["competition", "season", "home_team", "away_team", "status", "home_goals", "away_goals", "note"]
CANCELLED_STATUSES = {"CANCELLED", "CANCELED"}


def load_fixture_overrides(path, competition, season):
    """Read the committed overrides for one competition-season; a missing file means no overrides."""
    if path is None or not os.path.exists(path):
        return pd.DataFrame(columns=OVERRIDE_COLUMNS)
    overrides = pd.read_csv(path, dtype={"competition": str, "home_team": str, "away_team": str, "status": str, "note": str})
    missing = set(OVERRIDE_COLUMNS) - set(overrides.columns)
    if missing:
        raise ValueError(f"Fixture overrides file is missing columns: {sorted(missing)}")
    chosen = overrides[overrides["competition"].eq(competition) & overrides["season"].eq(season)]
    return chosen.reset_index(drop=True)


def resolve_fixture_statuses(matches, overrides=None, *, strict=False):
    """Decide how to treat cancelled or awarded fixtures without altering the fetched data.

    Returns a copy of `matches` whose `status` column is what the forecast uses, plus a
    `reported_status` column keeping the provider's value, and a list describing every change.
    Precedence: an explicit override, then an awarded result's reported score, then cancelled
    fixtures are treated as still to be played (league fixtures must be replayed or awarded).
    """
    out = matches.copy()
    out["reported_status"] = out["status"]
    adjustments = []

    def record(index, reason):
        row = out.loc[index]
        adjustments.append({
            "home": row["homeTeam"], "away": row["awayTeam"],
            "kickoff": row["utcDate"].isoformat() if pd.notna(row["utcDate"]) else None,
            "reported_status": row["reported_status"], "used_status": row["status"],
            "score": None if row["status"] != "FINISHED" else f"{int(row['homeGoals'])}-{int(row['awayGoals'])}",
            "reason": reason,
        })

    for override in (overrides if overrides is not None else pd.DataFrame(columns=OVERRIDE_COLUMNS)).itertuples(index=False):
        hit = out.index[out["homeTeam"].eq(override.home_team) & out["awayTeam"].eq(override.away_team)]
        if len(hit) != 1:
            raise ValueError(f"Fixture override {override.home_team} v {override.away_team} matches {len(hit)} fixtures.")
        status = str(override.status).upper()
        if status == "FINISHED":
            goals = pd.to_numeric(pd.Series([override.home_goals, override.away_goals]), errors="coerce")
            if goals.isna().any() or (goals < 0).any() or (goals != goals.round()).any():
                raise ValueError(f"Fixture override {override.home_team} v {override.away_team} needs both scores.")
            out.loc[hit, ["homeGoals", "awayGoals"]] = goals.astype(int).tolist()
        elif status == "SCHEDULED":
            out.loc[hit, ["homeGoals", "awayGoals"]] = None
        else:
            raise ValueError("Fixture overrides may only set status FINISHED (with a score) or SCHEDULED.")
        out.loc[hit, "status"] = status
        record(hit[0], f"override: {override.note}" if isinstance(override.note, str) and override.note else "override")

    pending = out["status"].eq(out["reported_status"])
    awarded = pending & out["status"].eq("AWARDED")
    for index in out.index[awarded]:
        goals = pd.to_numeric(out.loc[index, ["homeGoals", "awayGoals"]], errors="coerce")
        if goals.isna().any():
            raise ValueError(f"Awarded fixture {out.loc[index, 'homeTeam']} v {out.loc[index, 'awayTeam']} has no score; "
                             "add it to the fixture overrides file.")
        out.loc[index, "status"] = "FINISHED"
        record(index, "awarded result counted as played")

    cancelled = pending & out["status"].isin(CANCELLED_STATUSES)
    if cancelled.any() and strict:
        names = ", ".join(f"{r.homeTeam} v {r.awayTeam}" for r in out[cancelled].itertuples())
        raise ValueError(f"Cancelled fixtures need an override in strict mode: {names}")
    for index in out.index[cancelled]:
        out.loc[index, ["status", "homeGoals", "awayGoals"]] = ["SCHEDULED", None, None]
        record(index, "cancelled; simulated as if it will be replayed")
    if adjustments:
        warnings.warn("; ".join(f"{a['home']} v {a['away']}: {a['reason']}" for a in adjustments), stacklevel=2)
    return out, adjustments


def fill_lagging_results(matches, standings, results, *, as_of=None, max_kickoff_gap=pd.Timedelta(days=2)):
    """Fill past fixtures the provider still lists as unplayed although its own table counts them.

    football-data.org can update standings days before a match's status, so the table and the
    fixtures disagree and the forecast cannot run. A fixture is filled from `results` (another
    source's completed matches with homeTeam, awayTeam, utcDate, homeGoals and awayGoals, or a
    callable returning them, called only when something lags) when its kickoff has passed, both
    clubs' table rows count more games than their finished fixtures, and the pairing appears
    within `max_kickoff_gap` of kickoff. validate_schedule still checks the filled scores against
    the table's goal totals. Returns a copy and the adjustments made.
    """
    out = matches.copy()
    if "reported_status" not in out:
        out["reported_status"] = out["status"]
    as_of = pd.Timestamp.now(tz="UTC") if as_of is None else pd.to_datetime(as_of, utc=True)
    finished = out["status"].eq("FINISHED")
    counted = pd.concat([out.loc[finished, "homeTeam"], out.loc[finished, "awayTeam"]]).value_counts()
    table = standings.set_index("team")["played"]
    owed = (pd.to_numeric(table, errors="coerce") - counted.reindex(table.index).fillna(0)).to_dict()
    kickoffs = pd.to_datetime(out["utcDate"], utc=True, errors="coerce")
    lagging = (~finished & kickoffs.lt(as_of) & out["homeTeam"].map(owed).gt(0) & out["awayTeam"].map(owed).gt(0))
    if not lagging.any():
        return out, []
    results = results() if callable(results) else results
    if results is None or results.empty:
        return out, []
    source = results.assign(home_norm=results["homeTeam"].map(normalize_team), away_norm=results["awayTeam"].map(normalize_team))
    # Each home/away pairing occurs once per league season; duplicates make the match ambiguous.
    source = source.drop_duplicates(["home_norm", "away_norm"], keep=False).set_index(["home_norm", "away_norm"])
    adjustments = []
    for index in kickoffs[lagging].sort_values().index:
        home, away = out.at[index, "homeTeam"], out.at[index, "awayTeam"]
        key = (normalize_team(home), normalize_team(away))
        if key not in source.index or owed[home] <= 0 or owed[away] <= 0:
            continue
        row = source.loc[key]
        goals = pd.to_numeric(pd.Series([row["homeGoals"], row["awayGoals"]]), errors="coerce")
        if (goals.isna().any() or (goals < 0).any()
                or abs(pd.to_datetime(row["utcDate"], utc=True) - kickoffs[index]) > max_kickoff_gap):
            continue
        out.loc[index, ["homeGoals", "awayGoals"]] = goals.astype(int).tolist()
        out.loc[index, "status"] = "FINISHED"
        owed[home] -= 1
        owed[away] -= 1
        adjustments.append({
            "home": home, "away": away, "kickoff": kickoffs[index].isoformat(),
            "reported_status": out.at[index, "reported_status"], "used_status": "FINISHED",
            "score": f"{int(goals[0])}-{int(goals[1])}",
            "reason": "score from Understat while football-data.org catches up",
        })
    if adjustments:
        warnings.warn("; ".join(f"{a['home']} v {a['away']}: {a['reason']}" for a in adjustments), stacklevel=2)
    return out, adjustments


def rewind_season(matches, standings, as_of, *, competition="PD", delay=RESULT_DELAY):
    """The fixtures and table as they stood at `as_of`, rebuilt from today's complete data.

    A result counts once its kickoff is `delay` old; later results go back to scheduled. The table
    is rebuilt from the results that remain, ordered by the league's tie-breaks. Points in today's
    table that its results do not explain (deductions) are carried back, since the feed does not date
    them. Returns the rewound fixtures, the table and the carried point adjustments by team.
    """
    as_of = pd.to_datetime(as_of, utc=True)
    out = matches.copy()
    kickoff = pd.to_datetime(out["utcDate"], utc=True, errors="coerce")
    later = out["status"].eq("FINISHED") & ~(kickoff + delay <= as_of)
    out.loc[later, ["homeGoals", "awayGoals"]] = None
    out.loc[later, "status"] = "SCHEDULED"
    if "reported_status" in out:
        out.loc[later, "reported_status"] = "SCHEDULED"
    teams = standings["team"].tolist()
    explained = standings_from_matches(matches, teams=teams).set_index("team")["points"]
    adjustments = (standings.set_index("team")["points"] - explained.reindex(teams)).astype(int)
    table = standings_from_matches(out, teams=teams)
    table["points"] += table["team"].map(adjustments).to_numpy()
    order = rank_table(table, played_matches=out[out["status"].eq("FINISHED")], competition=competition)
    table = table.set_index("team").loc[order].reset_index()
    table["position"] = np.arange(1, len(table) + 1)
    return out, table[STANDING_COLUMNS], {team: int(points) for team, points in adjustments.items() if points}


def validate_schedule(matches, standings):
    required = {"homeTeam", "awayTeam", "status", "homeGoals", "awayGoals"}
    if not required.issubset(matches.columns):
        raise ValueError(f"Schedule is missing columns: {sorted(required - set(matches.columns))}")
    standing_required = {"team", "position", "played", "goals_for", "goals_against"}
    if not standing_required.issubset(standings.columns):
        raise ValueError(f"Standings are missing columns: {sorted(standing_required - set(standings.columns))}")
    if standings.empty or standings["team"].duplicated().any():
        raise ValueError("Standings must contain each team exactly once.")
    positions = pd.to_numeric(standings["position"], errors="coerce")
    if sorted(positions) != list(range(1, len(standings) + 1)):
        raise ValueError("Standings positions must be a permutation of 1 through the number of teams.")
    stat_columns = ["played", "goals_for", "goals_against"]
    reported = standings.set_index("team")[stat_columns].apply(pd.to_numeric, errors="coerce")
    stats = reported.to_numpy(dtype=float)
    if not np.isfinite(stats).all() or (stats < 0).any() or (stats != np.floor(stats)).any():
        raise ValueError("Standings played and goal totals must be nonnegative integers.")
    teams = set(standings["team"])
    participants = set(matches["homeTeam"]) | set(matches["awayTeam"])
    unknown = participants - teams
    if unknown:
        raise ValueError(f"Schedule contains teams absent from standings: {sorted(unknown)}")
    if matches[["homeTeam", "awayTeam"]].duplicated().any():
        raise ValueError("Schedule contains duplicate home/away pairings.")
    expected = {(home, away) for home in teams for away in teams if home != away}
    actual = set(zip(matches["homeTeam"], matches["awayTeam"]))
    if actual != expected:
        raise ValueError(f"Incomplete double round-robin schedule: {len(expected - actual)} missing fixtures, {len(actual - expected)} invalid fixtures.")
    if matches["status"].isna().any():
        raise ValueError("Schedule contains fixtures without a status.")
    unsupported = sorted(set(matches["status"]) & {"CANCELLED", "CANCELED", "AWARDED"})
    if unsupported:
        raise ValueError(f"Cannot simulate fixtures with status {', '.join(unsupported)}; resolve their official results first.")
    finished = matches[matches["status"].eq("FINISHED")]
    scores = finished[["homeGoals", "awayGoals"]].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(scores).all() or (scores < 0).any() or (scores != np.floor(scores)).any():
        raise ValueError("Finished fixtures must have nonnegative integer scores.")
    results = pd.DataFrame({
        "team": pd.concat([finished["homeTeam"], finished["awayTeam"]], ignore_index=True),
        "goals_for": np.concatenate([scores[:, 0], scores[:, 1]]),
        "goals_against": np.concatenate([scores[:, 1], scores[:, 0]]),
    })
    totals = results.groupby("team").agg(played=("team", "size"), goals_for=("goals_for", "sum"), goals_against=("goals_against", "sum"))
    totals = totals.reindex(reported.index, fill_value=0)
    for column in stat_columns:
        if not totals[column].eq(reported[column]).all():
            raise ValueError(f"Finished fixture {column} totals disagree with standings; refresh the data before forecasting.")
    remaining = matches[~matches["status"].eq("FINISHED")].copy()
    live = remaining["status"].isin(["IN_PLAY", "PAUSED", "LIVE", "EXTRA_TIME", "PENALTY_SHOOTOUT"])
    if live.any():
        warnings.warn(f"{int(live.sum())} fixtures are in progress; they will be simulated from kickoff.", stacklevel=2)
    return remaining


def standings_from_matches(matches, teams=None, competition="PD"):
    if teams is None:
        teams = pd.unique(matches[["homeTeam", "awayTeam"]].to_numpy().ravel())
    elif isinstance(teams, pd.DataFrame):
        teams = teams["team"]
    table = pd.DataFrame(0, index=pd.Index(list(teams), name="team"), columns=["played", "points", "goals_for", "goals_against"])
    finished = matches[matches["status"].eq("FINISHED")] if "status" in matches else matches
    for row in finished.itertuples(index=False):
        home, away = row.homeTeam, row.awayTeam
        hg, ag = int(row.homeGoals), int(row.awayGoals)
        if home not in table.index or away not in table.index:
            raise ValueError("Match contains a team absent from the requested standings.")
        table.loc[[home, away], "played"] += 1
        table.loc[home, ["goals_for", "goals_against"]] += [hg, ag]
        table.loc[away, ["goals_for", "goals_against"]] += [ag, hg]
        table.loc[home, "points"] += 3 if hg > ag else int(hg == ag)
        table.loc[away, "points"] += 3 if ag > hg else int(hg == ag)
    table["goal_diff"] = table["goals_for"] - table["goals_against"]
    table = table.reset_index().sort_values(["points", "goal_diff", "goals_for", "team"], ascending=[False, False, False, True]).reset_index(drop=True)
    table["position"] = np.arange(1, len(table) + 1)
    return table[STANDING_COLUMNS]
