import argparse
import hashlib
import html
import json
import math
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
COMPETITIONS = {
    "premier-league": "PL", "la-liga": "PD", "bundesliga": "BL1",
    "serie-a": "SA", "ligue-1": "FL1", "champions-league": "CL",
}
STAGES = {"round16": 16, "quarterfinal": 8, "semifinal": 4, "final": 2}
INDEX_FIELDS = ("slug", "code", "name", "country", "season", "generated_at")
STAKE_METRICS = ("title", "ucl", "releg", "top8", "top24")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def close(actual, expected, tolerance, message):
    require(abs(actual - expected) <= tolerance + 1e-9,
            f"{message}: expected {expected}, got {actual}")


def rounding(count):
    # Published cells lose 0.005 pp; intermediate domestic CSV cells lose 0.00005 pp.
    return count * 0.0051


def unique(rows, key):
    values = [row[key] for row in rows if row[key] is not None]
    require(len(values) == len(set(values)), f"duplicate {key}")


def finite(value):
    if isinstance(value, float):
        require(math.isfinite(value), "nonfinite number")
    elif isinstance(value, dict):
        for item in value.values():
            finite(item)
    elif isinstance(value, list):
        for item in value:
            finite(item)


@lru_cache
def validator(family):
    schema = json.loads((ROOT / "schemas/site/data.schema.json").read_text())
    require(family in schema["$defs"], f"unknown schema family {family}")
    formats = FormatChecker()
    require({"date", "date-time", "uri"} <= formats.checkers.keys(),
            "date/URI validators unavailable; install requirements-lock.txt")
    return Draft202012Validator({"$ref": f"#/$defs/{family}", "$defs": schema["$defs"]},
                               format_checker=formats)


def validate_competition(data):
    teams, zones = data["teams"], data["zones"]
    size = len(teams)
    for key in ("id", "slug"):
        unique(teams, key)
    if data["kind"] == "ucl":
        unique(teams, "key")
    require(sorted(team["position"] for team in teams) == list(range(1, size + 1)),
            "current positions must be a permutation of 1..team count")
    expected_zones = ["r16", "playoff", "out"] if data["kind"] == "ucl" else ["ucl", "europe", "releg"]
    require([zone["key"] for zone in zones] == expected_zones, "unexpected zone keys or ordering")
    for zone in zones:
        require(1 <= zone["from"] <= zone["to"] <= size, "zone outside table positions")
    for team in teams:
        probs = team["probs"]
        require(len(probs) == size, f"{team['slug']}: position vector length differs from team count")
        close(sum(probs), 100, rounding(size), f"{team['slug']}: position probability sum")
        require(team["xpos"] <= size, f"{team['slug']}: expected position outside table")
        expected = sum((i + 1) * p for i, p in enumerate(probs)) / 100
        close(team["xpos"], expected, rounding(size * (size + 1) / 2) / 100 + 0.0051,
              f"{team['slug']}: expected position")
        require(team["p10"] <= team["p90"], f"{team['slug']}: reversed points quantiles")
        for zone in zones:
            band = probs[zone["from"] - 1:zone["to"]]
            close(team[zone["key"]], sum(band), rounding(len(band) + 1),
                  f"{team['slug']}: {zone['key']} position band")
        if data["kind"] == "league":
            close(team["title"], probs[0], rounding(2), f"{team['slug']}: title probability")
        else:
            progression = [team["r16"] + team["playoff"],
                           *[team["stages"][stage] for stage in STAGES], team["title"]]
            require(all(a + rounding(3) >= b for a, b in zip(progression, progression[1:])),
                    f"{team['slug']}: tournament progression is not nested")
            require(team["r16"] <= team["stages"]["round16"] + rounding(2),
                    f"{team['slug']}: top-eight chance exceeds last-16 chance")
            close(team["r16"] + team["playoff"] + team["out"], 100, rounding(3),
                  f"{team['slug']}: league-phase outcome sum")
    for column in zip(*(team["probs"] for team in teams)):
        close(sum(column), 100, rounding(size), "position column probability sum")
    if data["kind"] == "ucl":
        for key, places in {"r16": 8, "playoff": 16, "out": 12, "title": 1}.items():
            close(sum(team[key] for team in teams), places * 100, rounding(size), f"{key} place total")
        for stage, places in STAGES.items():
            close(sum(team["stages"][stage] for team in teams), places * 100, rounding(size),
                  f"{stage} place total")
        validate_bracket(data)


def validate_bracket(data):
    by_name = {team["name"]: team["id"] for team in data["teams"]}
    require(len(by_name) == len(data["teams"]), "duplicate UCL display name")
    bracket = data["bracket"]
    for stage in ("playoffs", *STAGES):
        ties = bracket["stages"][stage]
        for tie in ties:
            require(tie["team1"] != tie["team2"], "bracket team plays itself")
            require(tie["winner"] in (tie["team1"], tie["team2"]), "bracket winner absent from tie")
            for field in ("team1", "team2", "winner"):
                require(tie[field] in by_name, f"unknown bracket team {tie[field]}")
                require(tie[f"{field}_id"] == by_name[tie[field]], f"bracket {field} ID mismatch")
    final = bracket["stages"]["final"][0]
    require((bracket["champion"], bracket["champion_id"]) == (final["winner"], final["winner_id"]),
            "bracket champion differs from final winner")
    seeds = bracket.get("seeds", [])
    require(len(seeds) <= 24 and len(seeds) == len(set(seeds)) and all(name in by_name for name in seeds),
            "invalid bracket seeds")


def validate_forecast(match, label):
    if "p" in match:
        close(sum(match["p"]), 1, 0.0002, f"{label}: outcome probability sum")
        scores = [score[2] for score in match["top"]]
        require(scores == sorted(scores, reverse=True), f"{label}: unsorted top scores")
    if "elo" in match:
        close(sum(match["elo"]), 1, 0.000002, f"{label}: Elo probability sum")
    if "stakes" in match:
        unique(match["stakes"]["teams"], "id")
        require(all(any(key in team for key in STAKE_METRICS)
                    for team in match["stakes"]["teams"]), "stakes team has no tracked metric")


def validate_matches(data):
    unique(data["matches"], "id")
    for match in data["matches"]:
        require(match["home_id"] is None or match["home_id"] != match["away_id"],
                f"match {match['id']}: club plays itself")
        validate_forecast(match, f"match {match['id']}")
        if "xg_source" in match:
            require("xg" in match, f"match {match['id']}: xG source without xG")
        if "xg_p" in match:
            require(match["status"] == "FINISHED" and "xg" in match, "on-chances probabilities require finished xG")
            close(sum(match["xg_p"]), 1, 1e-9, f"match {match['id']}: xG probability sum")
        if "miss" in match:
            require(match["status"] == "FINISHED" and "p" in match, "miss requires a finished forecast")
            require((match["miss"]["xg"] == "unknown") == ("xg" not in match), "miss xG coverage differs")
        if match.get("published"):
            require(match["status"] == "FINISHED" and "p" in match, "published match must have a finished forecast")
            require(datetime.fromisoformat(match["at"]) < datetime.fromisoformat(match["kickoff"]),
                    f"match {match['id']}: published forecast must precede kickoff")


def validate_forecast_receipts(data):
    for fixture_id, receipt in data["fixtures"].items():
        validate_forecast(receipt, f"receipt {fixture_id}")
        require(datetime.fromisoformat(receipt["generated_at"]) < datetime.fromisoformat(receipt["kickoff"]),
                f"receipt {fixture_id}: generated_at must precede kickoff")


def validate_match_events(data, fixture=None, *, consistency=True):
    require(len((json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode()) < 60_000,
            "match file must be under 60 KB")
    uefa = data["sources"].get("uefa")
    if uefa:
        require(data["competition"] == "champions-league", "UEFA detail requires Champions League")
        require(datetime.fromisoformat(uefa["fetched_at"]) >= datetime.fromisoformat(data["kickoff"]),
                "UEFA data fetched before kickoff")
    if any(key in data for key in ("physical", "heat", "positions")):
        require(uefa is not None and "physical" in data, "UEFA detail requires its source and physical players")
        for side in ("h", "a"):
            players = data["physical"][side]["players"]
            unique(players, "id")
            by_id = {row["id"]: row for row in players}
            if "heat" in data:
                heat = data["heat"][side]
                unique(heat["players"], "id")
                require(sum(heat["team"]) > 0, "empty UEFA team heatmap")
                require(all(row["id"] in by_id and by_id[row["id"]]["minutes"] >= 30 and sum(row["grid"]) > 0
                            for row in heat["players"]), "heatmap requires a player with at least 30 minutes")
                require(all(sum(row["grid"][i] for row in heat["players"]) <= cell for i, cell in enumerate(heat["team"])),
                        "player heatmaps exceed team activity")
            if "positions" in data:
                positions = data["positions"][side]
                unique(positions, "id")
                unique(positions, "number")
                require(all(row["id"] in by_id and row["player"] == by_id[row["id"]]["player"] for row in positions),
                        "average position has no matching physical player")
    if "retro" in data:
        close(sum(data["retro"]), 1, 1e-9, "retrospective probability sum")
    understat = data["sources"].get("understat")
    if understat:
        require(datetime.fromisoformat(understat["fetched_at"]) >= datetime.fromisoformat(data["kickoff"]),
                "Understat data fetched before kickoff")
    espn = data["sources"].get("espn")
    if espn:
        require(datetime.fromisoformat(espn["fetched_at"]) >= datetime.fromisoformat(data["kickoff"]),
                "ESPN data fetched before kickoff")
    if "box" in data or "events" in data:
        require(espn is not None, "ESPN detail requires its source")
    if "box" in data:
        box = data["box"]
        if "possession" in box:
            close(sum(box["possession"]), 100, 0.2, "possession sum")
        if "shots" in box and "shots_on_target" in box:
            require(all(a <= b for a, b in zip(box["shots_on_target"], box["shots"])),
                    "shots on target exceed shots")
    if "events" in data:
        events = data["events"]
        minutes = [event["minute"] for event in events]
        require(minutes == sorted(minutes), "ESPN events are not ordered by minute")
        require(all(event["minute"] == sum(map(int, event["clock"].split("+"))) for event in events),
                "ESPN minute differs from displayed clock")
        if espn:
            goals = [0, 0]
            for event in events:
                if event["type"] in ("goal", "penalty_goal", "own_goal"):
                    side = event["side"]
                    if event["type"] == "own_goal":
                        side = "a" if side == "h" else "h"
                    goals[0 if side == "h" else 1] += 1
            require(goals == espn["score"], "ESPN timeline goals differ from checked final score")
    if "players" in data:
        for side in ("h", "a"):
            unique(data["players"][side], "id")
    if fixture is None:
        return
    require(data["id"] == fixture["id"] and data["kickoff"] == fixture["kickoff"],
            "match event identity differs from fixture")
    require(fixture["status"] == "FINISHED", "match events require a finished fixture")
    if consistency and uefa:
        require(uefa["score"] == fixture["score"], "UEFA final score differs from fixture")
    if consistency and espn:
        require(espn["score"] == fixture["score"], "ESPN final score differs from fixture")
    if not consistency or "shots" not in data:
        return
    require("xg" in fixture, "shot consistency requires published match xg")
    for index, side in enumerate(("h", "a")):
        shots = [shot for shot in data["shots"] if shot[1] == side]
        # Understat's match xG counts shots from one attack as a single chance, 1 - prod(1 - xG), so the
        # per-shot sum can exceed it but never fall short.
        require(sum(shot[4] for shot in shots) >= fixture["xg"][index] - 0.05, f"{side} shot xG sum below match xG")
        opposite = "a" if side == "h" else "h"
        goals = sum(shot[5] == "Goal" for shot in shots)
        goals += (sum(player["own_goals"] for player in data["players"][opposite]) if "players" in data
                  else sum(shot[1] == opposite and shot[5] == "OwnGoal" for shot in data["shots"]))
        require(goals == fixture["score"][index], f"{side} shot goals plus opposition own goals differ from score")


def validate_clubs(data):
    clubs = data["clubs"]
    for key in ("id", "slug"):
        unique(clubs, key)
    for field in ("rating", "attack", "defense"):
        ranked = sorted(clubs, key=lambda club: club[f"{field}_rank"])
        require([club[f"{field}_rank"] for club in ranked] == list(range(1, len(clubs) + 1)),
                f"invalid {field} rank sequence")
        values = [club[field] for club in ranked]
        require(values == sorted(values, reverse=True), f"{field} ranks contradict ratings")
    require([club["rating_rank"] for club in clubs] == list(range(1, len(clubs) + 1)),
            "clubs are not ordered by overall rank")
    for league in set(club["league"] for club in clubs) - {None}:
        members = sorted((club for club in clubs if club["league"] == league), key=lambda club: club["league_rank"])
        require([club["league_rank"] for club in members] == list(range(1, len(members) + 1)),
                f"invalid {league} rank sequence")
        values = [club["rating"] for club in members]
        require(values == sorted(values, reverse=True), f"{league} ranks contradict ratings")
    require(len(data["featured"]) == len(set(data["featured"])) and
            set(data["featured"]) <= {club["id"] for club in clubs}, "invalid featured club reference")


def validate_profiles(data):
    for club, profile in data["clubs"].items():
        require(profile["from"] <= profile["to"], f"profile {club} dates are reversed")
        require(profile["form"]["games"][0] <= profile["form"]["games"][1] == profile["games"] <= data["window"],
                f"profile {club} game counts are inconsistent")
        close(sum(profile["state"]["minutes"]), 1, 1e-3, f"profile {club} game-state minute shares")
        for key in ("led", "trailed", "first"):
            require(profile["state"][key][1] <= profile["state"][key][0], f"profile {club} {key} count exceeds its games")
        for key, (_, rank, _, games) in profile["metrics"].items():
            require(games <= profile["games"], f"profile {club} {key} covers more games than the window")
            require(key in data["leagues"][profile["league"]], f"profile {club} {key} has no league mean")


def validate_history(data):
    unique(data["teams"], "id")
    require(data["dates"] == sorted(set(data["dates"])), "history dates must strictly increase")
    for team in data["teams"]:
        for metric in data["metrics"]:
            require(metric in team and len(team[metric]) == len(data["dates"]),
                    f"history team {team['id']}: {metric} series length differs from dates")


def validate_club_history(data):
    dates = [week["date"] for week in data["weeks"]]
    require(dates == sorted(set(dates)), "week dates must strictly increase")
    require(all(date.fromisoformat(day).weekday() == 0 for day in dates), "week date must be Monday")


def validate_rating_runs(data):
    times = [datetime.fromisoformat(run["as_of"]) for run in data["runs"]]
    require(all(a < b for a, b in zip(times, times[1:])), "rating run origins must strictly increase")
    require(all(time.tzinfo is not None and time.astimezone(timezone.utc).strftime("%Y-%m") == data["month"]
                for time in times), "rating run origin outside its month")


def validate_misses(row):
    n, misses = row["n"], row["misses"]
    matrix = misses["confusion"]
    require(sum(map(sum, matrix)) == n, "confusion matrix must sum to n")
    actual = misses["outcomes"]["actual"]
    require(sum(actual) == n, "actual outcomes must sum to n")
    require(actual == [sum(line[i] for line in matrix) for i in range(3)], "actual outcomes differ from confusion columns")
    close(sum(misses["outcomes"]["expected"]), n, max(1, n) * 1e-12, "expected outcomes must sum to n")
    counts = {kind: sum(value["xg"].values()) for kind, value in misses["kinds"].items()}
    require(sum(counts.values()) == n, "miss kinds must sum to n")
    require(counts["called"] == row["called"] == sum(matrix[i][i] for i in range(3)), "called count differs")
    require(counts["draw"] + counts["upset"] + counts["missed_draw_call"] == n - row["called"], "miss counts differ")
    require(counts["draw"] == matrix[0][1] + matrix[2][1], "draw misses differ from confusion matrix")
    require(counts["upset"] == matrix[0][2] + matrix[2][0], "upsets differ from confusion matrix")
    require(counts["missed_draw_call"] == matrix[1][0] + matrix[1][2], "missed draw calls differ from confusion matrix")
    xg_n = n - sum(value["xg"]["unknown"] for value in misses["kinds"].values())
    goals = misses["goals"]
    require(goals["team_games"] <= 2 * xg_n, "goal coverage exceeds xG coverage")
    for key in ("predicted", "goals", "xg", "mae_goals", "mae_xg"):
        require((goals[key] is None) == (goals["team_games"] == 0), "empty goal means must be null")
    for key, sample in misses["xg_scored"].items():
        require(sample["n"] <= xg_n, "xG score coverage exceeds xG coverage")
        if key == "model":
            require(sample["n"] == xg_n, "model xG score coverage differs")
        else:
            require(sample["n"] <= row["baselines"][key]["n"], "xG score coverage exceeds baseline coverage")
        for metric in ("log_loss", "real_log_loss"):
            require((sample[metric] is None) == (sample["n"] == 0), "empty xG scores must be null")


def validate_score_record(row):
    n = row["n"]
    require(row["model"]["n"] == n, "scorecard model count differs")
    require(row["n_published"] <= n and row["called"] <= n and row["exact"] <= n, "scorecard count exceeds n")
    close(sum(cell["n"] for cell in row["calibration"]), 3 * n, 0, "calibration outcome count")
    for i, cell in enumerate(row["calibration"]):
        require(cell["lo"] == i / 10 and cell["hi"] == (i + 1) / 10, "calibration bin edges differ")
        for key in ("probability", "observed"):
            require((cell[key] is None) == (cell["n"] == 0), "empty calibration bin must have null means")
    summaries = [row["model"], *row["baselines"].values(), *[b["model"] for b in row["baselines"].values()]]
    for baseline in row["baselines"].values():
        require(baseline["n"] <= n and baseline["model"]["n"] == baseline["n"], "baseline must compare the same fixtures")
    weeks = [point["week"] for point in row["weekly"]]
    require(weeks == sorted(set(weeks)), "scorecard weeks must strictly increase")
    require(all(date.fromisoformat(week).weekday() == 0 for week in weeks), "scorecard week must be Monday")
    for key in ("model", "frequency", "elo"):
        series = [point[key] for point in row["weekly"]]
        summaries.extend(series)
        require([point["n"] for point in series] == sorted(point["n"] for point in series), "cumulative counts must increase")
        final = row["model"] if key == "model" else row["baselines"][key]
        require((series[-1]["n"] if series else 0) == final["n"], "weekly endpoint count differs")
        if series:
            for metric in ("log_loss", "brier", "rps"):
                require(series[-1][metric] == final[metric], "weekly endpoint score differs")
    for summary in summaries:
        for key in ("log_loss", "brier", "rps"):
            require((summary[key] is None) == (summary["n"] == 0), "empty score must be null")
    require((row["avg_chance_given"] is None) == (n == 0), "empty chance given must be null")
    validate_misses(row)


def validate_scorecard(data):
    for entry in [*data["competitions"].values(), data["all"]]:
        for row in (entry, entry["published"], entry["reconstructed"]):
            validate_score_record(row)
        require(entry["n"] == entry["published"]["n"] + entry["reconstructed"]["n"], "cohort counts must sum")
        require(entry["n_published"] == entry["published"]["n"] and entry["reconstructed"]["n_published"] == 0,
                "published cohort count differs")
    for key in ("n", "n_published", "called", "exact"):
        require(data["all"][key] == sum(entry[key] for entry in data["competitions"].values()), "all-competition count differs")
    for entry in data["competitions"].values():
        baseline = entry["frequency_baseline"]
        if baseline:
            season = int(entry["season"][:4])
            require(baseline["requested_seasons"] == list(range(season - 5, season)), "frequency seasons must precede season")
            require(baseline["seasons"] == sorted(set(baseline["seasons"])) and
                    set(baseline["seasons"]) <= set(baseline["requested_seasons"]), "invalid frequency season coverage")
            if baseline["p"] is not None:
                require(len(baseline["seasons"]) == 5 and baseline["n"] > 0, "frequency needs five prior seasons")
                close(sum(baseline["p"]), 1, 1e-9, "frequency probability sum")


def validate_notes(data):
    seasons = data["seasons"]
    years = [int(season.split("/")[0]) for season in seasons]
    require(years == sorted(set(years)), "note coverage seasons must strictly increase")
    require(data["first_season"] == seasons[0], "first season differs from note coverage")


def validate_usage_sheet(game, detail, source, side):
    if game["reason"] == "invalid_match_sheet":
        return
    if source == "understat":
        rows = detail.get("players", {}).get(side) if source in detail.get("sources", {}) else None
        observed = None if rows is None else {row["id"]: (row["player"], row["minutes"], row["position"] != "Sub") for row in rows}
        positions = {}
    else:
        physical = detail.get("physical", {}).get(side)
        positions = {row["id"]: row for row in detail.get("positions", {}).get(side, [])}
        rows = physical["players"] if physical is not None and side in detail.get("positions", {}) and source in detail.get("sources", {}) else None
        observed = None if rows is None else {row["id"]: (row["player"], row["minutes"], row["id"] in positions) for row in rows}
    if game["status"] == "missing":
        require(observed is None, "usage marks an available sheet missing")
        return
    require(observed is not None and set(observed) == {r["source_id"] for r in game["appearances"]},
            "usage appearances differ from published sheet")
    for row in game["appearances"]:
        require((row["name"], row["minutes"], row["starter"]) == observed[row["source_id"]],
                "usage participation differs from published sheet")
        if source == "uefa" and row["starter"]:
            position = positions[row["source_id"]]
            for axis in ("x", "y"):
                expected = position[axis] if side == "h" else round(1 - position[axis], 4)
                require(row[f"avg_{axis}"] == expected, "usage position differs from published sheet")


def validate_squad_usage(data, by_id, formations):
    ids = {str(pid): pid for pid in by_id}
    require(("usage" in data) == ("usage_generated_at" in data), "usage needs its own generation time")
    if "usage" in data:
        require(datetime.fromisoformat(data["usage_generated_at"]) >= datetime.fromisoformat(data["generated_at"]),
                "usage generated before baseline")
    for slug, usage in data.get("usage", {}).items():
        source = "uefa" if slug == "champions-league" else "understat"
        require(usage["source"] == source, "usage source differs from competition")
        games = usage["games_list"]
        unique(games, "fixture_id")
        require([(g["kickoff"], g["fixture_id"]) for g in games] ==
                sorted((g["kickoff"], g["fixture_id"]) for g in games), "usage games out of order")
        require(usage["games"] == len(games), "usage game count differs")
        require(usage["covered"] == sum(g["reason"] in (None, "unmapped_appearances") for g in games), "usage coverage differs")
        require(usage["fully_mapped"] == sum(g["status"] == "complete" for g in games), "usage identity coverage differs")
        require(set(usage["players"]) == {str(pid) for pid in by_id}, "usage player set differs from squad")
        ideal = {s["player"] for s in data["ideal_xi"]["slots"] if s["player"] is not None}
        bindings = {}
        for game in games:
            rows = game["appearances"]
            unique(rows, "source_id")
            unique(rows, "player")
            require(all(row["player"] is None or row["player"] in by_id for row in rows), "unknown usage player")
            reason = game["reason"]
            expected = "missing" if reason == "missing_match_sheet" else "partial" if reason else "complete"
            require(game["status"] == expected, "usage game status differs from reason")
            if reason in {"missing_match_sheet", "invalid_match_sheet"}:
                require(not rows, "unusable sheet cannot have known appearances")
            else:
                require(game["sheet_sha256"] is not None, "observed sheet needs provenance")
                require(sum(row["starter"] for row in rows) == 11, "usage sheet needs eleven starters")
                require((reason is None) == all(row["player"] is not None for row in rows), "usage mapping status differs")
            for key, starter in (("starters", True), ("subs", False)):
                require(game[key] == [row["player"] for row in rows if row["player"] is not None and
                                      row["starter"] == starter], "usage lineup differs from appearances")
            known = set(game["starters"] + game["subs"])
            expected_ideal = (len(ideal & set(game["starters"])) if len(ideal) == 11 and
                              (game["status"] == "complete" or len(game["starters"]) == 11 or ideal <= known) else None)
            require(game["ideal_started"] == expected_ideal, "ideal starters count differs")
            for row in rows:
                require(("avg_x" in row) == ("avg_y" in row), "observed coordinates need both axes")
                require(("avg_x" in row) == (source == "uefa" and row["starter"]), "coordinates differ from source/starter")
                require(({"xg", "xa"} <= row.keys()) == (source == "understat"), "xG/xA differ from source")
                if row["player"] is not None:
                    require(bindings.setdefault(row["source_id"], row["player"]) == row["player"], "provider identity conflict")
        for pid, total in usage["players"].items():
            player_id = ids[pid]
            observed = [row for game in games for row in game["appearances"] if row["player"] == player_id]
            known = sum(g["status"] == "complete" or any(r["player"] == player_id for r in g["appearances"]) for g in games)
            require(total["known_games"] == known and total["unknown_games"] == len(games) - known,
                    "player known/unknown game counts differ")
            for key, expected in (("starts", sum(r["starter"] for r in observed)),
                                  ("sub", sum(not r["starter"] for r in observed)),
                                  ("minutes", round(sum(r["minutes"] for r in observed), 1))):
                require(total[key] == (expected if known else None), f"player {key} differs from sheets")
            expected_share = round(total["minutes"] / (90 * usage["covered"]), 6) if known and usage["covered"] else None
            require(total["share"] == expected_share, "player share differs from covered games")
            require(total["provider_ids"] == sorted({r["source_id"] for r in observed}), "player provider IDs differ")
            if source == "uefa":
                positions = [r for r in observed if "avg_x" in r]
                for key in ("avg_x", "avg_y"):
                    expected = round(sum(r[key] for r in positions) / len(positions), 4) if positions else None
                    require(key in total and total[key] == expected, "player average position differs")
            else:
                require(not {"avg_x", "avg_y"} & total.keys(), "domestic usage cannot have UEFA positions")
                for key in ("xg", "xa"):
                    require(total.get(key, "missing") == (round(sum(r[key] for r in observed), 4) if known else None),
                            f"player {key} differs from sheets")
        xi = usage["most_used_xi"]
        require([s["role"] for s in xi["slots"]] == formations[xi["formation"]], "most-used XI roles differ")
        unique(xi["slots"], "player")
        for slot in xi["slots"]:
            pid = slot["player"]
            if pid is None:
                continue
            require(pid in by_id, "most-used XI player absent from squad")
            ea = by_id[pid]["ea"]
            require(ea is not None and ea["overall"] is not None and (usage["players"][str(pid)]["minutes"] or 0) > 0,
                    "most-used XI player needs rated positions and observed minutes")
            eligible = {"LW": {"LW", "LM"}, "LM": {"LW", "LM"}, "RW": {"RW", "RM"}, "RM": {"RW", "RM"}}.get(slot["role"], {slot["role"]})
            require(bool(eligible & set(ea["positions"])), "most-used XI player ineligible for role")
        filled = sum(s["player"] is not None for s in xi["slots"])
        eligible_count = sum(bool(p["ea"] is not None and p["ea"]["overall"] is not None and p["ea"]["positions"] and
                                  (usage["players"][str(pid)]["minutes"] or 0) > 0) for pid, p in by_id.items())
        expected = "insufficient_coverage" if filled < 11 else "provisional" if eligible_count < len(by_id) else "complete"
        require(xi["status"] == expected, "most-used XI coverage differs")


def validate_squad(data):
    players = data["players"]
    listed = [row for row in players if row["status"] != "observed"]
    observed = [row for row in players if row["status"] == "observed"]
    unique(players, "id")
    matched = [row for row in players if row["status"] == "matched"]
    unique([row["ea"] for row in players if row["ea"]], "id")
    require(all((row["status"] == "matched") == (row["ea"] is not None) for row in listed),
            "only matched players can have EA ratings")
    require(all(isinstance(row["id"], int) for row in listed), "listed players need provider squad IDs")
    require(data["coverage"] == {"players": len(listed), "matched": len(matched)}, "squad coverage differs")
    require((data["roster"]["status"] == "available") == bool(listed), "roster availability differs from players")
    require(datetime.fromisoformat(data["roster"]["observed_at"]) <= datetime.fromisoformat(data["generated_at"]),
            "squad generated before roster observation")
    require(data["ratings"]["snapshot_date"] <= data["generated_at"][:10], "rating vintage after baseline creation")
    formations = {
        "4-3-3": ["GK", "LB", "CB", "CB", "RB", "CDM", "CM", "CM", "LW", "ST", "RW"],
        "4-2-3-1": ["GK", "LB", "CB", "CB", "RB", "CDM", "CDM", "CAM", "LW", "ST", "RW"],
        "4-4-2": ["GK", "LB", "CB", "CB", "RB", "CM", "CM", "LM", "RM", "ST", "ST"],
    }
    xi = data["ideal_xi"]
    require([slot["role"] for slot in xi["slots"]] == formations[xi["formation"]], "XI roles differ from formation")
    unique(xi["slots"], "player")
    by_id = {row["id"]: row for row in players}
    ratings = []
    for slot in xi["slots"]:
        if slot["player"] is None:
            continue
        require(slot["player"] in by_id, "XI player absent from squad")
        require(by_id[slot["player"]]["status"] == "matched", "ideal XI must use listed squad players")
        ea = by_id[slot["player"]]["ea"]
        require(ea is not None and ea["overall"] is not None, "XI player has no rating")
        role = slot["role"]
        eligible = {"LW": {"LW", "LM"}, "LM": {"LW", "LM"}, "RW": {"RW", "RM"}, "RM": {"RW", "RM"}}.get(role, {role})
        require(bool(eligible & set(ea["positions"])), "XI player ineligible for role")
        ratings.append(ea["overall"])
    fully_rated = all(row["ea"] is not None and row["ea"]["overall"] is not None and row["ea"]["positions"] for row in listed)
    expected = "insufficient_coverage" if len(ratings) < 11 else "complete" if fully_rated else "provisional"
    require(xi["status"] == expected, "XI coverage status differs")
    require(xi["mean_overall"] == (round(sum(ratings) / 11, 1) if len(ratings) == 11 else None),
            "XI mean differs from selected players")

    validate_squad_usage(data, by_id, formations)
    for player in observed:
        require(player["source"] == "match_sheet" and player["dob"] is None and player["provider_position"] is None,
                "observed player cannot claim provider squad membership or birth date")
        require((player["method"] in {"name_and_club", "unique_name"}) == (player["ea"] is not None),
                "observed EA match needs its name method")
        require(player["ea"] is not None or player.get("reason") in {"no_name_match", "ambiguous_name_match"},
                "unrated observed player needs a reason")
        require(player["name"].casefold() not in {p["name"].casefold() for p in listed}, "observed player duplicates listed name")
        providers, dates, counts = {}, [], []
        for usage in data.get("usage", {}).values():
            appearances = [(g, r) for g in usage["games_list"] for r in g["appearances"] if r["player"] == player["id"]]
            counts.append(len({g["fixture_id"] for g, _ in appearances}))
            if appearances:
                providers[usage["source"]] = {"ids": sorted({r["source_id"] for _, r in appearances}),
                                               "names": sorted({html.unescape(r["name"]) for _, r in appearances})}
                dates.extend(g["kickoff"][:10] for g, _ in appearances)
        require(max(counts, default=0) >= 2, "observed player needs two games in one competition")
        require(player["providers"] == providers and all(len(p["ids"]) == 1 for p in providers.values()),
                "observed provider identities differ from appearances")
        require(player["id"] in {f"observed:{source}:{sid}" for source, p in providers.items() for sid in p["ids"]},
                "observed player ID needs a provider namespace")
        require(player["name"] in {name for p in providers.values() for name in p["names"]}, "observed name absent from sheets")
        require(player["first_seen"] == min(dates) and player["last_seen"] == max(dates), "observed appearance dates differ")


def validate_backtest(data):
    columns = data["columns"]
    lengths = {key: len(values) for key, values in columns.items()}
    require(len(set(lengths.values())) == 1, "backtest columns have different lengths")
    rows = next(iter(lengths.values()), 0)
    coverage = data["coverage"]
    require(coverage["rows"] == rows, "backtest coverage rows differ from columns")
    require(coverage["replayed"] + coverage["published"] == rows,
            "backtest replayed and published coverage differ from rows")

    by_comp, seen, price_counts = {}, set(), {}
    missing_fields = {
        "missing_ids": lambda row: row["id"] is None or row["home_id"] is None or row["away_id"] is None,
        "missing_xg": lambda row: row["xg"] is None,
        "missing_exp": lambda row: row["exp"] is None,
        "missing_stakes": lambda row: row["stakes"] is None,
        "missing_matchday": lambda row: row["matchday"] is None,
        "missing_rating": lambda row: row["rating_gap"] is None,
    }
    for index in range(rows):
        row = {key: values[index] for key, values in columns.items()}
        kickoff = datetime.fromisoformat(row["kickoff"].replace("Z", "+00:00"))
        origin = datetime.fromisoformat(row["at"].replace("Z", "+00:00"))
        require(kickoff.utcoffset() == timezone.utc.utcoffset(kickoff),
                f"backtest row {index}: kickoff must be UTC")
        require(origin.utcoffset() == timezone.utc.utcoffset(origin),
                f"backtest row {index}: forecast origin must be UTC")
        require(origin < kickoff, f"backtest row {index}: forecast origin must precede kickoff")
        close(sum(row["p"]), 1, 1e-3, f"backtest row {index}: probability sum")
        if row["elo"] is not None:
            close(sum(row["elo"]), 1, 1e-3, f"backtest row {index}: Elo probability sum")
        fixture = (row["comp"], data["season"], row["home_key"], row["away_key"], row["forecast"])
        require(fixture not in seen, "duplicate backtest fixture and forecast")
        seen.add(fixture)
        counts = by_comp.setdefault(row["comp"], {"replayed": 0, "published": 0,
            **{key: 0 for key in missing_fields}})
        counts[row["forecast"]] += 1
        for key, missing in missing_fields.items():
            counts[key] += missing(row)
        if row["forecast"] == "published":
            require(all(book["pre"] is None for book in row["prices"].values()),
                    f"backtest row {index}: published rows cannot have pre-closing prices")
        for book, quotes in row["prices"].items():
            totals = price_counts.setdefault(book, {"pre": 0, "close": 0})
            for timing in ("pre", "close"):
                totals[timing] += quotes[timing] is not None

    require(coverage["replayed"] == columns["forecast"].count("replayed"),
            "backtest replayed coverage differs from rows")
    require(coverage["published"] == columns["forecast"].count("published"),
            "backtest published coverage differs from rows")
    require(set(coverage["by_comp"]) == set(by_comp), "backtest competition coverage keys differ from rows")
    for comp, actual in by_comp.items():
        declared = coverage["by_comp"][comp]
        for key, value in actual.items():
            require(declared.get(key) == value, f"backtest {comp} coverage {key} differs from rows")
    require(set(coverage["prices"]) == set(price_counts), "backtest price coverage books differ from rows")
    for book, actual in price_counts.items():
        require(coverage["prices"][book] == actual, f"backtest price coverage differs for {book}")


def validate_payload(data, family):
    finite(data)
    errors = list(validator(family).iter_errors(data))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "root"
        raise ValueError(f"{location}: {error.message}")
    if family in ("league", "ucl"):
        validate_competition(data)
    elif family == "index":
        unique(data, "slug")
    elif family == "matches":
        validate_matches(data)
    elif family == "forecast_receipts":
        validate_forecast_receipts(data)
    elif family == "match_events":
        validate_match_events(data)
    elif family == "scorecard":
        validate_scorecard(data)
    elif family == "clubs":
        validate_clubs(data)
    elif family == "profiles":
        validate_profiles(data)
    elif family == "history":
        validate_history(data)
    elif family == "club_history":
        validate_club_history(data)
    elif family == "rating_runs":
        validate_rating_runs(data)
    elif family == "notes":
        validate_notes(data)
    elif family == "squad":
        validate_squad(data)
    elif family == "backtest":
        validate_backtest(data)


def file_family(path):
    parts = path.parts
    if len(parts) == 2 and parts == ("backtest", "index.json"):
        return "backtest_index"
    if len(parts) == 1:
        if path.stem in ("index", "clubs", "crests", "scorecard", "profiles"):
            return path.stem
        if path.stem in COMPETITIONS:
            return "ucl" if path.stem == "champions-league" else "league"
    if len(parts) == 2 and parts[0] == "backtest" and path.stem.isdigit():
        return "backtest"
    if len(parts) == 2 and parts[0] == "matches" and path.stem in COMPETITIONS:
        return "matches"
    if len(parts) == 2 and parts[0] == "notes" and path.stem in COMPETITIONS:
        return "notes"
    if (len(parts) == 4 and parts[0] == "match" and parts[1].isdigit()
            and parts[2] in COMPETITIONS and path.stem.isdigit() and int(path.stem) > 0):
        return "match_events"
    if len(parts) == 3 and parts[0] == "squads" and parts[1].isdigit():
        return "squad"
    if len(parts) == 3 and parts[0] == "history" and parts[1].isdigit():
        if path.stem == "clubs":
            return "club_history"
        if path.stem in COMPETITIONS:
            return "history"
    if (len(parts) == 4 and parts[0] == "history" and parts[1].isdigit()
            and parts[2] == "forecasts" and path.stem in COMPETITIONS):
        return "forecast_receipts"
    if len(parts) == 4 and parts[0] == "history" and parts[1].isdigit() and parts[2] == "ratings":
        return "rating_runs"
    raise ValueError("unknown JSON file family")


def reject_constant(value):
    raise ValueError(f"nonfinite JSON number {value}")


def validate_site_data(data_dir, *, site_dir=None):
    data_dir = Path(data_dir)
    site_dir = Path(site_dir) if site_dir is not None else data_dir.parent
    files, errors = {}, []
    for path in sorted(data_dir.rglob("*.json")):
        relative = path.relative_to(data_dir)
        try:
            family = file_family(relative)
            data = json.loads(path.read_text(), parse_constant=reject_constant)
            validate_payload(data, family)
            if family in ("league", "ucl", "matches", "history", "forecast_receipts"):
                require(data["slug"] == path.stem, "slug differs from filename")
            if family in ("league", "ucl"):
                require(data["code"] == COMPETITIONS[path.stem], "competition code differs from slug")
            if relative.parts[0] == "history":
                require(data["season"].split("/")[0] == relative.parts[1], "history season differs from directory")
            if family == "squad":
                require(data["slug"] == path.stem, "squad slug differs from filename")
                require(data["season"] == relative.parts[1], "squad season differs from directory")
            if family == "rating_runs":
                require(data["month"] == path.stem, "rating month differs from filename")
            if family == "backtest":
                require(data["season"] == int(path.stem), "backtest season differs from filename")
            if family == "match_events":
                require(path.stat().st_size < 60_000, "match file must be under 60 KB")
                require(data["id"] == int(path.stem), "match event id differs from filename")
                require(data["competition"] == relative.parts[2], "match event competition differs from directory")
            files[relative.as_posix()] = data
        except (OSError, ValueError) as exc:
            errors.append(f"{relative}: {exc}")
    required = {"index.json", "clubs.json",
                *(f"{slug}.json" for slug in COMPETITIONS)}
    errors.extend(f"{name}: required valid file missing" for name in sorted(required - files.keys()))
    backtest_index = files.get("backtest/index.json")
    if backtest_index is not None:
        for season in backtest_index["seasons"]:
            name = f"backtest/{season}.json"
            if name not in files:
                errors.append(f"backtest/index.json: listed season file missing ({season})")
    for entry in files.get("index.json", []):
        table = files.get(f"{entry['slug']}.json")
        if table is not None and any(entry[key] != table[key] for key in INDEX_FIELDS):
            errors.append(f"index.json: {entry['slug']} metadata differs from table")
    if "index.json" in files and {entry["slug"] for entry in files["index.json"]} != set(COMPETITIONS):
        errors.append("index.json: competition set differs from required tables")
    for name, data in files.items():
        if Path(name).parts[0] != "notes":
            continue
        slug = Path(name).stem
        matches = files.get(f"matches/{slug}.json")
        table = files.get(f"{slug}.json")
        if table is not None:
            if data["as_of"] != table["as_of"]:
                errors.append(f"{name}: forecast origin differs from competition")
            if data["generated_at"] != table["generated_at"]:
                errors.append(f"{name}: generation time differs from competition")
        if matches is not None:
            fixture_ids = {str(row["id"]) for row in matches["matches"]}
            if not set(data["fixtures"]) <= fixture_ids:
                errors.append(f"{name}: note references an unknown fixture")
    for club in files.get("clubs.json", {}).get("clubs", []):
        if club["league"] is not None and f"{club['league']}.json" not in files:
            errors.append(f"clubs.json: unresolved league {club['league']}")
    profiles = files.get("profiles.json")
    if profiles and profiles["season"] == files.get("clubs.json", {}).get("season"):
        leagues = {club["id"]: club["league"] for club in files["clubs.json"]["clubs"]}
        if any(leagues.get(int(club)) != profile["league"] for club, profile in profiles["clubs"].items()):
            errors.append("profiles.json: club identity or league differs from clubs.json")
    for name, data in files.items():
        parts = Path(name).parts
        if parts[0] != "match":
            continue
        table = files.get(f"{data['competition']}.json", {})
        if table.get("season", "").split("/")[0] != parts[1]:
            continue
        matches = files.get(f"matches/{data['competition']}.json")
        if matches is None:
            continue
        fixture = next((row for row in matches["matches"] if row["id"] == data["id"]), None)
        try:
            require(fixture is not None, "match events have no current-season fixture")
            validate_match_events(data, fixture, consistency=False)
        except ValueError as exc:
            errors.append(f"{name}: {exc}")
    clubs = {club["slug"]: club for club in files.get("clubs.json", {}).get("clubs", [])}
    current_season = files.get("clubs.json", {}).get("season", "")[:4]
    for name, data in files.items():
        if Path(name).parts[0] == "squads" and data["season"] == current_season:
            club = clubs.get(data["slug"])
            if club is None or club["id"] != data["club_id"]:
                errors.append(f"{name}: squad identity differs from clubs.json")
    for name, squad in files.items():
        if Path(name).parts[0] != "squads" or "usage" not in squad:
            continue
        try:
            supported = {slug for slug in COMPETITIONS if files.get(f"{slug}.json", {}).get("season", "")[:4] == squad["season"]
                         and squad["club_id"] in {t["id"] for t in files[f"{slug}.json"]["teams"]}}
            if squad["season"] == current_season:
                require(set(squad["usage"]) == supported, "usage competition set differs from club participation")
            for slug, usage in squad["usage"].items():
                if slug not in supported:
                    continue  # Historical seasons need not have today's fixtures.
                fixtures = {f["id"]: f for f in files.get(f"matches/{slug}.json", {}).get("matches", [])}
                for game in usage["games_list"]:
                    fixture = fixtures.get(game["fixture_id"])
                    require(fixture is not None and fixture["status"] == "FINISHED", "usage game has no finished fixture")
                    require(fixture["kickoff"] == game["kickoff"], "usage kickoff differs from fixture")
                    require(squad["club_id"] in (fixture["home_id"], fixture["away_id"]), "usage club absent from fixture")
                    side = "h" if squad["club_id"] == fixture["home_id"] else "a"
                    require(game["opponent_id"] == fixture["away_id" if side == "h" else "home_id"], "usage opponent differs")
                    match_name = f"match/{squad['season']}/{slug}/{game['fixture_id']}.json"
                    if match_name in files and game["sheet_sha256"] is not None:
                        digest = hashlib.sha256((data_dir / match_name).read_bytes()).hexdigest()
                        if digest == game["sheet_sha256"]:
                            validate_usage_sheet(game, files[match_name], usage["source"], side)
        except ValueError as exc:
            errors.append(f"{name}: {exc}")
    for crest in files.get("crests.json", {}).values():
        if not (site_dir / crest["path"]).is_file():
            errors.append(f"crests.json: missing asset {crest['path']}")
    if errors:
        raise ValueError("\n".join(errors))
    return len(files)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate the published site JSON and local crest references.")
    parser.add_argument("--data", type=Path, default=ROOT / "site/data")
    parser.add_argument("--site", type=Path)
    args = parser.parse_args(argv)
    try:
        count = validate_site_data(args.data, site_dir=args.site)
    except ValueError as exc:
        parser.exit(1, f"{exc}\n")
    print(f"Validated {count} site data files")


if __name__ == "__main__":
    main()
