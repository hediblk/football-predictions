import argparse
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
    elif family == "history":
        validate_history(data)
    elif family == "club_history":
        validate_club_history(data)
    elif family == "rating_runs":
        validate_rating_runs(data)
    elif family == "notes":
        validate_notes(data)


def file_family(path):
    parts = path.parts
    if len(parts) == 1:
        if path.stem in ("index", "clubs", "crests", "scorecard"):
            return path.stem
        if path.stem in COMPETITIONS:
            return "ucl" if path.stem == "champions-league" else "league"
    if len(parts) == 2 and parts[0] == "matches" and path.stem in COMPETITIONS:
        return "matches"
    if len(parts) == 2 and parts[0] == "notes" and path.stem in COMPETITIONS:
        return "notes"
    if (len(parts) == 4 and parts[0] == "match" and parts[1].isdigit()
            and parts[2] in COMPETITIONS and path.stem.isdigit() and int(path.stem) > 0):
        return "match_events"
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
            if family == "rating_runs":
                require(data["month"] == path.stem, "rating month differs from filename")
            if family == "match_events":
                require(path.stat().st_size < 60_000, "match file must be under 60 KB")
                require(data["id"] == int(path.stem), "match event id differs from filename")
                require(data["competition"] == relative.parts[2], "match event competition differs from directory")
            files[relative.as_posix()] = data
        except (OSError, ValueError) as exc:
            errors.append(f"{relative}: {exc}")
    required = {"index.json", "clubs.json", *(f"{slug}.json" for slug in COMPETITIONS)}
    errors.extend(f"{name}: required valid file missing" for name in sorted(required - files.keys()))
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
