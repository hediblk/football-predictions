"""Export forecast outputs into the compact JSON files the static site reads.

Usage: python scripts/build_site_data.py [--src out/site] [--dest site/data]

Reads `<prefix>_summary.csv`, `<prefix>_position_probs.csv`, `<prefix>_standings_snapshot.csv`,
`<prefix>_matches_snapshot.csv`, `<prefix>_club_ratings.csv`, `<prefix>_match_forecasts.json` and
`<prefix>_metadata.json` for each league, plus the `cl_*` files for the Champions League.
"""

import argparse
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd


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
# Average team rating of each league's clubs in the Opta Power Rankings (0-100 global scale), used to put
# within-league club ratings on one scale. Opta updates these daily; refresh this table now and then.
LEAGUE_STRENGTH = {"PL": 92.7, "BL1": 86.6, "PD": 86.4, "SA": 85.7, "FL1": 85.5}
LEAGUE_STRENGTH_SOURCE = {
    "name": "Opta Power Rankings, average team rating by league", "date": "2026-10-12",
    "url": "https://dataviz.theanalyst.com/opta-power-rankings/?leagueRankings=true",
}
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
        "generated_at": meta["generated_at"], "data_cutoff": meta["data_cutoff"], "n_sim": meta["n_sim"],
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
        "generated_at": meta["generated_at"], "data_cutoff": meta["as_of"], "n_sim": meta["n_sim"],
        "played_fixtures": validation["finished"], "remaining_fixtures": validation["remaining"],
        "zones": zones_json(UCL_ZONES), "teams": teams,
        "bracket": {"stages": stages, "champion": label(bracket["champion"]), "champion_id": ids.get(bracket["champion"]), "note": bracket["draw_label"]},
    }


def export_matches(src, slug, prefix):
    """Every fixture with its forecast; played matches carry the forecast made before their match day."""
    data = json.loads((src / f"{prefix}_match_forecasts.json").read_text())
    display = data.get("display_names", {})
    name = lambda team: short_name(display.get(team, team))
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
        matches.append(row)
    matches.sort(key=lambda row: (row["kickoff"] or "", row["id"]))
    return {"slug": slug, "generated_at": data["generated_at"], "rule": data.get("played_forecast_rule"), "matches": matches}


def export_clubs(src, leagues, ucl, previous=None):
    """Club ratings from each league's model, scaled by league strength onto one scale, with ranks.

    A league without fresh ratings keeps its clubs from `previous` (the last published file).
    """
    in_ucl = {team["id"] for team in ucl["teams"]}
    strongest = max(LEAGUE_STRENGTH.values())
    clubs, kept = [], []
    factors = {league["slug"]: round(LEAGUE_STRENGTH[league["code"]] / strongest, 4) for league in leagues}
    for league in leagues:
        path = src / f"{league['code'].lower()}_club_ratings.csv"
        if not path.exists():
            clubs += [club for club in (previous or {}).get("clubs", []) if club["league"] == league["slug"]]
            kept.append(league["slug"])
            continue
        ratings = pd.read_csv(path).set_index("team")
        factor = factors[league["slug"]]
        for team in league["teams"]:
            row = ratings.loc[team["full"]]
            clubs.append({
                "id": team["id"], "slug": team["slug"], "name": team["name"], "full": team["full"],
                "league": league["slug"], "ucl": team["id"] in in_ucl,
                "rating": num(factor * row["rating"], 1), "attack": num(factor * row["attack_rating"], 1),
                "defense": num(factor * row["defense_rating"], 1), "home": num(factor * row["home_rating"], 1),
                "away": num(factor * row["away_rating"], 1), "league_rating": num(row["rating"], 1),
                "gf": num(row["goals_for"]), "ga": num(row["goals_against"]),
            })
    for field in ("rating", "attack", "defense"):
        for rank, club in enumerate(sorted(clubs, key=lambda club: -club[field]), start=1):
            club[f"{field}_rank"] = rank
    for league in leagues:
        members = sorted((club for club in clubs if club["league"] == league["slug"]), key=lambda club: -club["rating"])
        for rank, club in enumerate(members, start=1):
            club["league_rank"] = rank
    clubs.sort(key=lambda club: club["rating_rank"])
    if kept:
        print(f"Club ratings unavailable for {', '.join(kept)}; kept their previous entries")
    return {
        "generated_at": max(league["generated_at"] for league in leagues), "season": ucl["season"],
        "league_factors": factors, "league_strength": LEAGUE_STRENGTH_SOURCE,
        "featured": [club_id for club_id in FEATURED_CLUBS if any(club["id"] == club_id for club in clubs)],
        "clubs": clubs,
    }


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--src", type=Path, default=Path("out/site"))
    parser.add_argument("--dest", type=Path, default=Path("site/data"))
    args = parser.parse_args(argv)
    args.dest.mkdir(parents=True, exist_ok=True)
    jobs = [(league[0], lambda league=league: export_league(args.src, *league)) for league in LEAGUES]
    jobs.append(("champions-league", lambda: export_ucl(args.src)))
    jobs += [(f"matches/{league[0]}", lambda league=league: export_matches(args.src, league[0], league[1].lower()))
             for league in LEAGUES]
    jobs.append(("matches/champions-league", lambda: export_matches(args.src, "champions-league", "cl")))
    exports, kept, missing = {}, [], []
    for slug, export in jobs:
        path = args.dest / f"{slug}.json"
        try:
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
    index = [{key: data[key] for key in ("slug", "code", "name", "country", "season", "generated_at")} for data in competitions]
    (args.dest / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n")
    print(f"Wrote site data to {args.dest}" + (f"; kept previous data for {', '.join(kept)}" if kept else "")
          + (f"; no data yet for {', '.join(missing)}" if missing else ""))


if __name__ == "__main__":
    main()
