"""Export forecast outputs into the compact JSON files the static site reads.

Usage: python scripts/build_site_data.py [--src out/site] [--dest site/data]

Reads `<prefix>_summary.csv`, `<prefix>_position_probs.csv`, `<prefix>_standings_snapshot.csv`,
`<prefix>_matches_snapshot.csv`, `<prefix>_club_ratings.csv`, `<prefix>_match_forecasts.json` and
`<prefix>_metadata.json` for each league, plus the `cl_*` files for the Champions League.
Each fresh forecast also adds a point to `history/<season>/<slug>.json`, and the first refresh of a
week freezes the club ratings into `history/<season>/clubs.json` (see standing_prediction.site_history).
"""

import argparse
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd

from champions_league.identities import AREA_LEAGUES, COUNTRY_LEAGUES, canonical_team
from standing_prediction import site_history


LEAGUES = [
    # slug, code, name, country, zones as (key, label, first, last)
    ("premier-league", "PL", "Premier League", "England",
     [("ucl", "Champions League", 1, 4), ("europe", "Europe", 5, 6), ("releg", "Relegation", 18, 20)]),
    ("la-liga", "PD", "La Liga", "Spain",
     [("ucl", "Champions League", 1, 4), ("europe", "Europe", 5, 6), ("releg", "Relegation", 18, 20)]),
    ("bundesliga", "BL1", "Bundesliga", "Germany",
     [("ucl", "Champions League", 1, 4), ("europe", "Europe", 5, 6), ("releg", "Relegation", 16, 18)]),
    ("serie-a", "SA", "Serie A", "Italy",
     [("ucl", "Champions League", 1, 4), ("europe", "Europe", 5, 6), ("releg", "Relegation", 18, 20)]),
    ("ligue-1", "FL1", "Ligue 1", "France",
     [("ucl", "Champions League", 1, 4), ("europe", "Europe", 5, 6), ("releg", "Relegation", 16, 18)]),
]
UCL_ZONES = [("r16", "Round of 16", 1, 8), ("playoff", "Knockout play-offs", 9, 24), ("out", "Eliminated", 25, 36)]
UCL_STAGES = ["round16", "quarterfinal", "semifinal", "final"]
# What's at stake: domestic title/top-four/relegation, Champions League top eight/top 24/winner.
STAKE_METRICS = ("title", "ucl", "releg", "top8", "top24")
FORECAST_FIELDS = ("p", "exp", "top", "call", "btts", "o25", "stakes")
# The Champions League model's league codes, for clubs from outside the five leagues.
COUNTRIES = {code: area for area, code in AREA_LEAGUES.items()}
COUNTRY_CODES = {code: short for short, code in COUNTRY_LEAGUES.items()}

SHORT_NAMES = {
    "Brighton & Hove Albion FC": "Brighton", "Tottenham Hotspur FC": "Tottenham", "AFC Bournemouth": "Bournemouth",
    "Wolverhampton Wanderers FC": "Wolves", "West Ham United FC": "West Ham", "Nottingham Forest FC": "Nottingham Forest",
    "FC Bayern München": "Bayern München", "Bayer 04 Leverkusen": "Leverkusen", "1. FSV Mainz 05": "Mainz 05",
    "Borussia Dortmund": "Dortmund",
    "SV 07 Elversberg": "Elversberg", "TSG 1899 Hoffenheim": "Hoffenheim", "Borussia Mönchengladbach": "Gladbach",
    "FC Schalke 04": "Schalke 04", "SC Paderborn 07": "Paderborn", "FC St. Pauli 1910": "St. Pauli",
    "FC Internazionale Milano": "Inter", "Internazionale Milano": "Inter", "AC Milan": "Milan",
    "Olympique Lyonnais": "Lyon", "Olympique de Marseille": "Marseille", "Stade Rennais FC 1901": "Rennes",
    "Stade Brestois 29": "Brest", "Racing Club de Lens": "Lens", "RC Strasbourg Alsace": "Strasbourg",
    "Paris Saint-Germain FC": "Paris SG", "Club Atlético de Madrid": "Atlético Madrid",
    "Real Betis Balompié": "Real Betis", "Real Sociedad de Fútbol": "Real Sociedad",
    "RCD Espanyol de Barcelona": "Espanyol", "Rayo Vallecano de Madrid": "Rayo Vallecano",
    "RC Celta de Vigo": "Celta Vigo", "RC Deportivo La Coruña": "Deportivo", "Real Racing Club de Santander": "Racing Santander",
    "Sporting Clube de Portugal": "Sporting CP", "Sport Lisboa e Benfica": "Benfica", "FK Bodø/Glimt": "Bodø/Glimt",
    "Manchester United FC": "Man United", "Manchester City FC": "Man City", "Paris FC": "Paris FC",
    "Deportivo Alavés": "Alavés", "PAE AEK": "AEK Athens", "FK Shakhtar Donetsk": "Shakhtar",
    "Feyenoord Rotterdam": "Feyenoord", "LASK Linz": "LASK",
}
# The big clubs the Clubs tab opens with, by football-data.org team id.
FEATURED_CLUBS = [81, 86, 78, 5, 4, 524, 108, 98, 109, 64, 65, 57]
AFFIXES = r"^(?:FC|AFC|CF|AC|ACF|AS|SS|SSC|US|SC|SV|RC|RCD|CA|UD|SD|OGC|AJ|ES|BC|FK|SK|ŠK|VfB|VfL|1\.)\s+|\s+(?:FC|AFC|CF|CFC|BC|OSC|SCO|AC|UD|FK|SK|KV|Calcio|\d{4}|\d{2})$"


def short_name(name):
    if name in SHORT_NAMES:
        return SHORT_NAMES[name]
    previous = None
    while previous != name:
        previous, name = name, re.sub(AFFIXES, "", name).strip()
    return name


def slugify(name):
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")


def num(value, digits=2):
    return round(float(value), digits)


def team_ids(matches):
    """football-data.org team ids by provider name, from a matches snapshot."""
    pairs = pd.concat([matches[["homeTeam", "homeTeamId"]].set_axis(["team", "id"], axis=1),
                       matches[["awayTeam", "awayTeamId"]].set_axis(["team", "id"], axis=1)])
    return {team: int(team_id) for team, team_id in pairs.dropna().drop_duplicates("team").itertuples(index=False)}


def zone_probabilities(row, zones):
    return {key: num(sum(row[str(p)] for p in range(first, last + 1))) for key, _, first, last in zones}


def zones_json(zones):
    return [{"key": key, "label": label, "from": first, "to": last} for key, label, first, last in zones]


def export_league(src, slug, code, name, country, zones):
    prefix = code.lower()
    summary = pd.read_csv(src / f"{prefix}_summary.csv", index_col=0)
    probs = pd.read_csv(src / f"{prefix}_position_probs.csv", index_col=0)
    standings = pd.read_csv(src / f"{prefix}_standings_snapshot.csv").set_index("team")
    ids = team_ids(pd.read_csv(src / f"{prefix}_matches_snapshot.csv"))
    meta = json.loads((src / f"{prefix}_metadata.json").read_text())
    teams = []
    for team in summary.sort_values(["expected_position", "expected_points"], ascending=[True, False]).index:
        row, now = summary.loc[team], standings.loc[team]
        teams.append({
            "id": ids.get(team), "slug": slugify(short_name(team)), "name": short_name(team), "full": team,
            "position": int(now["position"]), "played": int(now["played"]), "points": int(now["points"]),
            "gd": int(now["goal_diff"]),
            "xpts": num(row["expected_points"], 1), "p10": int(row["points_p10"]), "p90": int(row["points_p90"]),
            "xpos": num(row["expected_position"]),
            "title": num(row["title_pct"]),
            "probs": [num(v) for v in probs.loc[team]],
            **zone_probabilities(probs.loc[team], zones),
        })
    return {
        "slug": slug, "kind": "league", "code": code, "name": name, "country": country,
        "season": f"{meta['season']}/{str(meta['season'] + 1)[-2:]}",
        "generated_at": meta["generated_at"], "as_of": meta.get("as_of", meta["generated_at"]),
        "data_cutoff": meta["data_cutoff"], "n_sim": meta["n_sim"],
        "played_fixtures": meta["finished_fixtures"], "remaining_fixtures": meta["remaining_fixtures"],
        "zones": zones_json(zones), "teams": teams,
        "fixture_notes": [{
            "home": short_name(note["home"]), "away": short_name(note["away"]), "kickoff": note["kickoff"],
            "reported_status": note["reported_status"], "used_status": note["used_status"],
            "score": note["score"], "reason": note["reason"],
        } for note in meta.get("fixture_adjustments", [])],
    }


def export_ucl(src):
    forecast = json.loads((src / "cl_forecast.json").read_text())
    meta = json.loads((src / "cl_metadata.json").read_text())
    standings = pd.read_csv(src / "cl_standings_snapshot.csv").set_index("team")
    ids = team_ids(pd.read_csv(src / "cl_matches_snapshot.csv"))
    names = meta["data"]["display_names"]
    label = lambda key: short_name(names.get(key, key.title()))
    summary = pd.DataFrame(forecast["summary"]).T
    teams = []
    for key in summary.sort_values(["expected_position", "expected_points"], ascending=[True, False]).index:
        row, now = summary.loc[key], standings.loc[key]
        probs = forecast["position_probabilities_pct"][key]
        teams.append({
            "key": key, "id": ids.get(key), "slug": slugify(label(key)), "name": label(key), "full": names.get(key, key),
            "position": int(now["position"]), "played": int(now["played"]), "points": int(now["points"]),
            "gd": int(now["goal_diff"]),
            "xpts": num(row["expected_points"], 1), "p10": int(row["points_p10"]), "p90": int(row["points_p90"]),
            "xpos": num(row["expected_position"]),
            "probs": [num(probs[str(p)]) for p in range(1, len(summary) + 1)],
            "r16": num(row["top8_pct"]), "playoff": num(row["playoffs_pct"]), "out": num(row["eliminated_pct"]),
            "stages": {stage: num(row[f"{stage}_pct"]) for stage in UCL_STAGES},
            "title": num(row["title_pct"]),
        })
    bracket = forecast["bracket"]
    stages = {
        stage: [{
            "team1": label(tie["team1"]), "team2": label(tie["team2"]), "winner": label(tie["winner"]),
            "team1_id": ids.get(tie["team1"]), "team2_id": ids.get(tie["team2"]), "winner_id": ids.get(tie["winner"]),
            "advance": num(tie["advance_probability"], 1), "observed": bool(tie["observed"]),
        } for tie in ties]
        for stage, ties in bracket["stages"].items()
    }
    validation = meta["league_validation"]
    return {
        "slug": "champions-league", "kind": "ucl", "code": "CL", "name": "Champions League", "country": "Europe",
        "season": f"{meta['season']}/{str(meta['season'] + 1)[-2:]}",
        "generated_at": meta["generated_at"], "as_of": meta["as_of"],
        "data_cutoff": meta.get("data_cutoff") or meta["as_of"], "n_sim": meta["n_sim"],
        "played_fixtures": validation["finished"], "remaining_fixtures": validation["remaining"],
        "zones": zones_json(UCL_ZONES), "teams": teams,
        "bracket": {"stages": stages, "champion": label(bracket["champion"]), "champion_id": ids.get(bracket["champion"]), "note": bracket["draw_label"],
                    # league-phase places behind the draw, so the site can mark the top eight and play-off seeds
                    "seeds": [label(team) for team in bracket.get("projected_league_order", [])[:24]]},
    }


def match_stakes(src, prefix, name=short_name):
    """The next round's `{n, teams}` stakes by match id, teams sorted by their biggest swing (empty without the file)."""
    path = src / f"{prefix}_stakes.json"
    if not path.exists():
        return {}
    ids = team_ids(pd.read_csv(src / f"{prefix}_matches_snapshot.csv"))
    swing = lambda entry: max(max(v for v in values if v is not None) - min(v for v in values if v is not None)
                              for key, values in entry.items() if key in STAKE_METRICS)
    stakes = {}
    for fixture in json.loads(path.read_text())["fixtures"]:
        teams = [{"id": ids.get(team), "name": name(team), **entry} for team, entry in fixture["teams"].items()]
        stakes[fixture["id"]] = {"n": fixture["n"], "teams": sorted(teams, key=swing, reverse=True)}
    return stakes


def export_matches(src, slug, prefix, receipts=None):
    data = json.loads((src / f"{prefix}_match_forecasts.json").read_text())
    display = data.get("display_names", {})
    name = lambda team: short_name(display.get(team, team))
    stakes = match_stakes(src, prefix, name)
    matches = []
    for match in data["matches"]:
        row = {
            "id": match["id"], "kickoff": match["utcDate"], "status": match["status"],
            "md": int(match["matchday"]) if match.get("matchday") is not None else None,
            "home": name(match["homeTeam"]), "away": name(match["awayTeam"]),
            "home_id": match.get("homeTeamId"), "away_id": match.get("awayTeamId"),
        }
        if match.get("reported_status") not in (None, match["status"]):
            row["reported"] = match["reported_status"]
        if match.get("stage"):
            row["stage"] = match["stage"]
        if match.get("neutral"):
            row["neutral"] = True
        if match["status"] == "FINISHED":
            row["score"] = [int(match["homeGoals"]), int(match["awayGoals"])]
        if match.get("home_xg") is not None and match.get("away_xg") is not None:
            row["xg"] = [num(match["home_xg"]), num(match["away_xg"])]
        if "p_home" in match:
            row.update({
                "p": [num(match[key], 4) for key in ("p_home", "p_draw", "p_away")],
                "exp": [num(match["exp_home_goals"]), num(match["exp_away_goals"])],
                "top": [[home, away, num(p, 4)] for home, away, p in match["scorelines"]],
                "btts": num(match["btts"], 3), "o25": num(match["over_2_5"], 3), "at": match["forecast_at"],
            })
            if "pick_score" in match:
                home, away, p = match["pick_score"]
                row["call"] = [home, away, num(p, 4)]
            if "p_score" in match:
                row["p_score"] = num(match["p_score"], 4)
        if match["status"] != "FINISHED" and match["id"] in stakes:
            row["stakes"] = stakes[match["id"]]
        receipt = (receipts or {}).get(str(match["id"]))
        if match["status"] == "FINISHED" and receipt:
            for key in (*FORECAST_FIELDS, "p_score"):
                row.pop(key, None)
            row.update({key: receipt[key] for key in FORECAST_FIELDS if key in receipt})
            row.update(at=receipt["generated_at"], published=True)
            for home, away, p in [*receipt["top"], *([receipt["call"]] if "call" in receipt else [])]:
                if row["score"] == [home, away]:
                    row["p_score"] = p
                    break
        matches.append(row)
    matches.sort(key=lambda row: (row["kickoff"] or "", row["id"]))
    rule = "Finished fixtures use published forecasts saved before kickoff where available; otherwise reconstructed forecasts as of 00:00 UTC on match day, from results before then."
    return {"slug": slug, "generated_at": data["generated_at"], "rule": rule, "matches": matches}


def club_entry(team, row, league, ucl):
    return {
        "id": team["id"], "slug": team["slug"], "name": team["name"], "full": team["full"],
        "league": league, "ucl": ucl,
        "rating": num(row["rating"], 1), "attack": num(row["attack_rating"], 1),
        "defense": num(row["defense_rating"], 1), "home": num(row["home_rating"], 1),
        "away": num(row["away_rating"], 1), "league_rating": num(row["league_rating"], 1),
        "gf": num(row["goals_for"]), "ga": num(row["goals_against"]),
    }


def export_clubs(src, leagues, ucl, previous=None):
    """Club ratings on one European scale from the Champions League joint model, with ranks.

    Ratings are shares of points against an average European top-flight club (`cl_club_ratings.csv`),
    so leagues compare through the model's league offsets. Every club in the five leagues is ranked, plus the
    Champions League clubs from elsewhere (`league` null, with their country). Without fresh ratings the previous
    file is kept; a club missing from them keeps its previous entry.
    """
    path = src / "cl_club_ratings.csv"
    if not path.exists():
        if previous is None:
            raise FileNotFoundError(path)
        print("Club ratings unavailable; kept the previous file")
        return previous
    ratings = pd.read_csv(path).set_index("team")
    earlier = {club["id"]: club for club in (previous or {}).get("clubs", [])}
    in_ucl = {team["id"] for team in ucl["teams"]}
    clubs, missing = [], []
    for league in leagues:
        for team in league["teams"]:
            key = canonical_team(team["full"])
            if key not in ratings.index:
                missing.append(team["name"])
                if team["id"] in earlier:
                    clubs.append(earlier[team["id"]])
                continue
            clubs.append(club_entry(team, ratings.loc[key], league["slug"], team["id"] in in_ucl))
    domestic = {team["id"] for league in leagues for team in league["teams"]}
    for team in ucl["teams"]:
        if team["id"] in domestic:
            continue
        if team["key"] not in ratings.index:
            missing.append(team["name"])
            if team["id"] in earlier:
                clubs.append(earlier[team["id"]])
            continue
        row = ratings.loc[team["key"]]
        code = str(row["league"])
        country = COUNTRIES.get(code, code.removeprefix("country:"))
        clubs.append({**club_entry(team, row, None, True), "country": country,
                      "country_code": COUNTRY_CODES.get(code, country[:3].upper()), "league_rank": None})
    for field in ("rating", "attack", "defense"):
        for rank, club in enumerate(sorted(clubs, key=lambda club: -club[field]), start=1):
            club[f"{field}_rank"] = rank
    for league in leagues:
        members = sorted((club for club in clubs if club["league"] == league["slug"]), key=lambda club: -club["rating"])
        for rank, club in enumerate(members, start=1):
            club["league_rank"] = rank
    clubs.sort(key=lambda club: club["rating_rank"])
    if missing:
        print(f"No European-scale rating for {', '.join(missing)}; kept previous entries where available")
    averages = {league["slug"]: num(sum(c["rating"] for c in clubs if c["league"] == league["slug"])
                                    / max(1, sum(c["league"] == league["slug"] for c in clubs)), 1) for league in leagues}
    return {
        "generated_at": ucl["generated_at"], "season": ucl["season"],
        "scale": {"reference": "average European top-flight club", "clubs": len(ratings), "leagues": int(ratings["league"].nunique())},
        "league_averages": averages,
        "featured": [club_id for club_id in FEATURED_CLUBS if any(club["id"] == club_id for club in clubs)],
        "clubs": clubs,
    }


def rated_clubs(src, leagues, ucl):
    """{football-data.org id: (rating, attack, defense)} for every club in the five leagues and the
    Champions League, from `cl_club_ratings.csv`; None without fresh ratings."""
    path = src / "cl_club_ratings.csv"
    if not path.exists():
        return None
    ratings = pd.read_csv(path).set_index("team")
    keys = {team["id"]: canonical_team(team["full"]) for league in leagues for team in league["teams"]}
    keys.update({team["id"]: team["key"] for team in ucl["teams"] if team["id"] not in keys})
    return {club_id: tuple(ratings.loc[key, ["rating", "attack_rating", "defense_rating"]])
            for club_id, key in keys.items() if club_id is not None and key in ratings.index}


def history_path(dest, data, name):
    return dest / "history" / site_history.season_key(data["season"]) / f"{name}.json"


def read_json(path):
    return json.loads(path.read_text()) if path.exists() else None


def publish_matches(src, dest, competition, prefix):
    slug = competition["slug"]
    path = history_path(dest, competition, f"forecasts/{slug}")
    history = read_json(path) or {"slug": slug, "season": competition["season"], "fixtures": {}}
    receipts = history["fixtures"]
    data = export_matches(src, slug, prefix, receipts)
    now = pd.Timestamp.now(tz="UTC")
    generated = pd.Timestamp(competition["generated_at"])
    changed = False
    for match in data["matches"]:
        previous = receipts.get(str(match["id"]))
        if previous and pd.Timestamp(previous["kickoff"]) <= now:
            continue
        if match["status"] == "FINISHED" or "p" not in match or pd.Timestamp(match["kickoff"]) <= max(now, generated):
            continue
        receipt = {
            "kickoff": match["kickoff"], "generated_at": competition["generated_at"],
            **{key: match[key] for key in FORECAST_FIELDS if key in match},
        }
        if receipt != previous:
            receipts[str(match["id"])] = receipt
            changed = True
    if changed:
        write_json(path, history)
    return data


def update_history(dest, competitions, ratings=None):
    """Add each fresh forecast to its competition's history and freeze the week's club ratings."""
    for data in competitions:
        path = history_path(dest, data, data["slug"])
        try:
            history = site_history.add_point(read_json(path), data, data["as_of"][:10])
        except ValueError as exc:
            print(f"History unchanged: {exc}")
            continue
        write_json(path, history)
    ucl = next((data for data in competitions if data["kind"] == "ucl"), None)
    if ratings and ucl:
        path = history_path(dest, ucl, "clubs")
        history, added = site_history.freeze_week(read_json(path), ratings, as_of=ucl["as_of"], season=ucl["season"],
                                                  cutoff=ucl["data_cutoff"])
        if added:
            write_json(path, history)
            print(f"Froze the club ranking for the week of {history['weeks'][-1]['date']}")


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--src", type=Path, default=Path("out/site"))
    parser.add_argument("--dest", type=Path, default=Path("site/data"))
    parser.add_argument("--history", action=argparse.BooleanOptionalAction, default=True,
                        help="Add season history points and weekly ratings (default: on; match receipts are always saved)")
    args = parser.parse_args(argv)
    args.dest.mkdir(parents=True, exist_ok=True)
    jobs = [(league[0], lambda league=league: export_league(args.src, *league)) for league in LEAGUES]
    jobs.append(("champions-league", lambda: export_ucl(args.src)))
    jobs += [(f"matches/{league[0]}", lambda league=league: publish_matches(args.src, args.dest, exports[league[0]], league[1].lower()))
             for league in LEAGUES]
    jobs.append(("matches/champions-league", lambda: publish_matches(args.src, args.dest, exports["champions-league"], "cl")))
    exports, kept, missing = {}, [], []
    for slug, export in jobs:
        path = args.dest / f"{slug}.json"
        try:
            if slug.startswith("matches/") and slug.split("/")[1] in kept:
                raise FileNotFoundError(slug)
            data = export()
        except FileNotFoundError:
            # No fresh outputs (e.g. the forecast run failed): keep the last published file.
            if path.exists():
                data = json.loads(path.read_text())
                kept.append(slug)
            elif slug.startswith("matches/"):
                missing.append(slug)  # The site shows these fixtures as unavailable.
                continue
            else:
                raise
        else:
            write_json(path, data)
        exports[slug] = data
    competitions = [exports[league[0]] for league in LEAGUES] + [exports["champions-league"]]
    clubs_path = args.dest / "clubs.json"
    previous = json.loads(clubs_path.read_text()) if clubs_path.exists() else None
    write_json(clubs_path, export_clubs(args.src, competitions[:-1], competitions[-1], previous))
    if args.history:
        fresh = [data for data in competitions if data["slug"] not in kept]
        ucl_fresh = "champions-league" not in kept
        update_history(args.dest, fresh, rated_clubs(args.src, competitions[:-1], competitions[-1]) if ucl_fresh else None)
    index = [{key: data[key] for key in ("slug", "code", "name", "country", "season", "generated_at")} for data in competitions]
    (args.dest / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n")
    print(f"Wrote site data to {args.dest}" + (f"; kept previous data for {', '.join(kept)}" if kept else "")
          + (f"; no data yet for {', '.join(missing)}" if missing else ""))


if __name__ == "__main__":
    main()
