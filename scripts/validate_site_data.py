import argparse
import json
import math
from datetime import date
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


def validate_matches(data):
    unique(data["matches"], "id")
    for match in data["matches"]:
        require(match["home_id"] is None or match["home_id"] != match["away_id"],
                f"match {match['id']}: club plays itself")
        if "p" in match:
            close(sum(match["p"]), 1, 0.0002, f"match {match['id']}: outcome probability sum")
            scores = [score[2] for score in match["top"]]
            require(scores == sorted(scores, reverse=True), f"match {match['id']}: unsorted top scores")
        if "stakes" in match:
            unique(match["stakes"]["teams"], "id")
            require(all(any(key in team for key in STAKE_METRICS)
                        for team in match["stakes"]["teams"]), "stakes team has no tracked metric")


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
    elif family == "clubs":
        validate_clubs(data)
    elif family == "history":
        validate_history(data)
    elif family == "club_history":
        validate_club_history(data)


def file_family(path):
    parts = path.parts
    if len(parts) == 1:
        if path.stem in ("index", "clubs", "crests"):
            return path.stem
        if path.stem in COMPETITIONS:
            return "ucl" if path.stem == "champions-league" else "league"
    if len(parts) == 2 and parts[0] == "matches" and path.stem in COMPETITIONS:
        return "matches"
    if len(parts) == 3 and parts[0] == "history" and parts[1].isdigit():
        if path.stem == "clubs":
            return "club_history"
        if path.stem in COMPETITIONS:
            return "history"
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
            if family in ("league", "ucl", "matches", "history"):
                require(data["slug"] == path.stem, "slug differs from filename")
            if family in ("league", "ucl"):
                require(data["code"] == COMPETITIONS[path.stem], "competition code differs from slug")
            if relative.parts[0] == "history":
                require(data["season"].split("/")[0] == relative.parts[1], "history season differs from directory")
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
    for club in files.get("clubs.json", {}).get("clubs", []):
        if club["league"] is not None and f"{club['league']}.json" not in files:
            errors.append(f"clubs.json: unresolved league {club['league']}")
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
