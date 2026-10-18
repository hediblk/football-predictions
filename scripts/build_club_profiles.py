import argparse
import csv
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

from standing_prediction.utils import normalize_team
from validate_site_data import validate_payload


ROOT = Path(__file__).resolve().parents[1]
UNDERSTAT = {"premier-league": "EPL", "la-liga": "La_liga", "bundesliga": "Bundesliga", "serie-a": "Serie_A", "ligue-1": "Ligue_1"}
WINDOW, FORM, MIN_GAMES = 38, 6, 5
STRONG, VERY = 0.8, 1.5  # standard deviations of the true club spread
BOX_EDGE = 0.843  # 16.5 m of a 105 m pitch, in Understat's 0-1 length
SET_PIECES = {"FromCorner", "SetPiece", "DirectFreekick"}
# key: (data needed, +1 when more is better, -1 when less is, 0 for a style)
METRICS = {
    "chances": ("shots", 1), "chances_against": ("shots", -1),
    "finishing": ("shots", 1), "saving": ("shots", -1),
    "set_pieces": ("shots", 1), "set_pieces_against": ("shots", -1),
    "headers": ("shots", 1), "headers_against": ("shots", -1),
    "long_shots": ("shots", 1),
    "crosses": ("actions", 1), "crosses_against": ("actions", -1),
    "through_balls": ("actions", 1), "through_balls_against": ("actions", -1),
    "dribbles": ("actions", 1), "dribbles_against": ("actions", -1),
    "cards": ("box", -1), "offsides": ("box", -1),
    "possession": ("box", 0), "fouls": ("box", 0), "offside_trap": ("box", 0),
    "long_shot_share": ("shots", 0), "cross_share": ("actions", 0),
}


def points(diff):
    return 3 if diff > 0 else 1 if diff == 0 else 0


# Each metric as (numerator, denominator) for one club in one game; None where the data is missing.
def game_values(shots, side, box):
    other = "a" if side == "h" else "h"

    def xg(team, keep):
        return sum(s[4] for s in shots if s[0] == team and s[5] != "OwnGoal" and keep(s))

    def count(team, keep):
        return sum(1 for s in shots if s[0] == team and s[5] != "OwnGoal" and keep(s))

    open_play = lambda s: s[6] == "OpenPlay"
    after = lambda action: lambda s: open_play(s) and s[8] == action
    np_goals = lambda team: count(team, lambda s: s[5] == "Goal" and s[6] != "Penalty")
    values = {
        "chances": xg(side, lambda s: s[6] != "Penalty"), "chances_against": xg(other, lambda s: s[6] != "Penalty"),
        "set_pieces": xg(side, lambda s: s[6] in SET_PIECES), "set_pieces_against": xg(other, lambda s: s[6] in SET_PIECES),
        "headers": xg(side, lambda s: s[7] == "Head"), "headers_against": xg(other, lambda s: s[7] == "Head"),
        "long_shots": xg(side, lambda s: s[2] < BOX_EDGE and s[6] != "Penalty"),
    }
    values["finishing"] = np_goals(side) - values["chances"]
    values["saving"] = np_goals(other) - values["chances_against"]
    values = {key: (value, 1) for key, value in values.items()}
    values["long_shot_share"] = (count(side, lambda s: s[2] < BOX_EDGE and s[6] != "Penalty"),
                                 count(side, lambda s: s[6] != "Penalty"))
    actions = all(s[8] is not None for s in shots)
    for key, action in (("crosses", "Cross"), ("through_balls", "Throughball"), ("dribbles", "TakeOn")):
        values[key] = (xg(side, after(action)), 1) if actions else None
        values[f"{key}_against"] = (xg(other, after(action)), 1) if actions else None
    values["cross_share"] = (count(side, after("Cross")), count(side, open_play)) if actions else None
    i, j = (0, 1) if side == "h" else (1, 0)
    stats = {
        "possession": ("possession", i), "fouls": ("fouls", i), "offsides": ("offsides", i), "offside_trap": ("offsides", j),
    }
    for key, (stat, index) in stats.items():
        values[key] = (box[stat][index], 1) if box and stat in box else None
    values["cards"] = (box["yellow"][i] + box["red"][i], 1) if box and "yellow" in box and "red" in box else None
    return values


def game_state(shots, side):
    goals = sorted((s[1], 1 if (s[0] == side) == (s[5] == "Goal") else -1) for s in shots if s[5] in ("Goal", "OwnGoal"))
    end = max([90] + [s[1] + 1 for s in shots])
    minutes, diff, last = [0, 0, 0], 0, 0
    led = trailed = False
    for minute, sign in goals:
        minutes[0 if diff > 0 else 1 if diff == 0 else 2] += minute - last
        diff, last = diff + sign, minute
        led, trailed = led or diff > 0, trailed or diff < 0
    minutes[0 if diff > 0 else 1 if diff == 0 else 2] += end - last
    at75 = sum(sign for minute, sign in goals if minute < 75)
    return {"minutes": minutes, "end": end, "diff": diff, "at75": at75, "led": led, "trailed": trailed,
            "first": goals[0][1] if goals else 0}


def record(club, date, season, shots, side, box):
    state = game_state(shots, side)
    values = game_values(shots, side, box)
    return {"club": club, "date": date, "season": season, "values": values, "state": state,
            "xgd": values["chances"][0] - values["chances_against"][0], "points": points(state["diff"])}


def current_games(data_dir, season, slug, league_ids):
    fixtures = {row["id"]: row for row in json.loads((data_dir / "matches" / f"{slug}.json").read_text())["matches"]}
    games = []
    for path in sorted((data_dir / "match" / season / slug).glob("*.json")):
        match = json.loads(path.read_text())
        fixture = fixtures.get(match["id"])
        if "shots" not in match or not fixture or fixture["status"] != "FINISHED":
            continue
        shots = [(s[1], s[0], s[2], s[3], s[4], s[5], s[6], s[7], s[10] if len(s) > 10 else None) for s in match["shots"]]
        for side, club in (("h", fixture["home_id"]), ("a", fixture["away_id"])):
            if club in league_ids:
                games.append(record(club, fixture["kickoff"][:10], int(season), shots, side, match.get("box")))
    return games


def archived_games(path, season, names):
    if not path.exists():
        return []
    matches = {}
    with gzip.open(path, "rt", newline="") as handle:
        for row in csv.DictReader(handle):
            match = matches.setdefault(row["match_id"], {"row": row, "shots": []})
            match["shots"].append((row["side"], int(row["minute"]), float(row["x"]), float(row["y"]), float(row["xg"]),
                                   row["result"], row["situation"], row["body"], row["last_action"]))
    games = []
    for match in matches.values():
        row = match["row"]
        for side, team in (("h", row["home"]), ("a", row["away"])):
            club = names.get(normalize_team(team))
            if club is not None:
                games.append(record(club, row["date"][:10], season, match["shots"], side, None))
    return games


# Each club's rate is shrunk toward its league's by the empirical-Bayes ratio of game-to-game noise to the true
# spread between clubs; z is the shrunk rate's distance from the league mean in units of that spread.
def estimate(windows, league_of, key):
    sums = {}
    for club, games in windows.items():
        covered = [g["values"][key] for g in games if g["values"][key] is not None and g["values"][key][1] > 0]
        num, den = sum(v[0] for v in covered), sum(v[1] for v in covered)
        if den > 0:
            sums[club] = (num, den, covered)
    league_mean = {}
    for league in set(league_of.values()):
        rows = [sums[c] for c in sums if league_of[c] == league]
        league_mean[league] = sum(r[0] for r in rows) / sum(r[1] for r in rows)
    residual = sum((v[0] - num / den * v[1]) ** 2 for num, den, covered in sums.values() for v in covered)
    dof = sum(den * (len(covered) - 1) / len(covered) for num, den, covered in sums.values())
    within = residual / dof
    spread = sum((num / den - league_mean[league_of[c]]) ** 2 for c, (num, den, _) in sums.items()) / len(sums)
    between = max(spread - within * sum(1 / den for _, den, _ in sums.values()) / len(sums), within * 1e-6)
    k, tau = within / between, between ** 0.5
    out = {}
    for club, (num, den, covered) in sums.items():
        mean = league_mean[league_of[club]]
        shrunk = (num + k * mean) / (den + k)
        out[club] = (num / den, shrunk, (shrunk - mean) / tau, len(covered))
    return out, league_mean


def run_in(fixtures, rating, club):
    played, left = [], []
    for m in fixtures:
        if club in (m["home_id"], m["away_id"]):
            opponent = m["away_id"] if m["home_id"] == club else m["home_id"]
            (played if m["status"] == "FINISHED" else left).append(rating[opponent])
    mean = lambda values: sum(values) / len(values) if values else None
    return {"played": mean(played), "left": mean(left), "games": len(left)}


def build(data_dir, archive_dir):
    clubs = json.loads((data_dir / "clubs.json").read_text())
    season = clubs["season"][:4]
    rating = {c["id"]: c["rating"] for c in clubs["clubs"]}
    league_of, windows, run_ins = {}, {}, {}
    for slug, provider in UNDERSTAT.items():
        members = [c for c in clubs["clubs"] if c["league"] == slug]
        ids = {c["id"] for c in members}
        names = {normalize_team(name): c["id"] for c in members for name in (c["name"], c["full"])}
        games = current_games(data_dir, season, slug, ids)
        games += archived_games(archive_dir / provider / f"{int(season) - 1}.csv.gz", int(season) - 1, names)
        fixtures = json.loads((data_dir / "matches" / f"{slug}.json").read_text())["matches"]
        for club in ids:
            mine = sorted((g for g in games if g["club"] == club), key=lambda g: g["date"], reverse=True)[:WINDOW]
            if mine:
                league_of[club], windows[club] = slug, mine
            run_ins[club] = run_in(fixtures, rating, club)
        hardest = sorted((c for c in ids if run_ins[c]["left"] is not None), key=lambda c: -run_ins[c]["left"])
        for club in ids:
            run_ins[club]["rank"] = hardest.index(club) + 1 if club in hardest else None
    estimates, league_means = {}, {}
    for key in METRICS:
        estimates[key], league_means[key] = estimate(windows, league_of, key)
    profiles = {}
    for club, games in windows.items():
        metrics = {}
        for key, (_, direction) in METRICS.items():
            if club not in estimates[key]:
                continue
            raw, shrunk, z, n = estimates[key][club]
            rivals = [estimates[key][c][1] for c in estimates[key] if league_of[c] == league_of[club]]
            sign = direction or 1
            rank = 1 + sum(sign * other > sign * shrunk for other in rivals)
            score = direction * z if direction else z
            level = 0 if n < MIN_GAMES else (2 if score >= VERY else 1 if score >= STRONG else
                                             -2 if score <= -VERY else -1 if score <= -STRONG else 0)
            if not direction:
                level = max(-1, min(1, level))
            metrics[key] = [round(raw, 4), rank, level, n]
        states = [g["state"] for g in games]
        late = [points(s["diff"]) - points(s["at75"]) for s in states]
        minutes = [sum(s["minutes"][i] for s in states) for i in range(3)]
        recent = games[:FORM]
        per_game = lambda rows, key: round(sum(g[key] for g in rows) / len(rows), 3)
        profiles[str(club)] = {
            "league": league_of[club], "games": len(games), "seasons": sorted({g["season"] for g in games}),
            "from": games[-1]["date"], "to": games[0]["date"],
            "metrics": metrics,
            "form": {"games": [len(recent), len(games)], "xgd": [per_game(recent, "xgd"), per_game(games, "xgd")],
                     "ppg": [per_game(recent, "points"), per_game(games, "points")]},
            "state": {
                "minutes": [round(m / sum(minutes), 4) for m in minutes],
                "late": [sum(x for x in late if x > 0), -sum(x for x in late if x < 0)],
                "led": [sum(s["led"] for s in states), sum(s["led"] and s["diff"] > 0 for s in states)],
                "trailed": [sum(s["trailed"] for s in states), sum(s["trailed"] and s["diff"] >= 0 for s in states)],
                "first": [sum(s["first"] > 0 for s in states), sum(s["first"] > 0 and s["diff"] > 0 for s in states)],
            },
        }
    for club, value in run_ins.items():
        if str(club) in profiles:
            profiles[str(club)]["run_in"] = {k: round(v, 2) if isinstance(v, float) else v for k, v in value.items()}
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "season": clubs["season"],
        "window": WINDOW, "form": FORM,
        "leagues": {slug: {key: round(league_means[key][slug], 4) for key in METRICS if slug in league_means[key]}
                    for slug in UNDERSTAT},
        "clubs": profiles,
    }


def main():
    parser = argparse.ArgumentParser(description="Describe each league club's play from its last league games' shots and match stats.")
    parser.add_argument("--data", type=Path, default=ROOT / "site/data")
    parser.add_argument("--archive", type=Path, default=ROOT / "data/shots")
    args = parser.parse_args()
    profiles = build(args.data, args.archive)
    validate_payload(profiles, "profiles")
    path = args.data / "profiles.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(profiles, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")
    temporary.replace(path)
    print(f"Profiles: {len(profiles['clubs'])} clubs")


if __name__ == "__main__":
    main()
