"""Export forecast outputs into the compact JSON files the static site reads.

Usage: python scripts/build_site_data.py [--src out/site] [--dest site/data]

Reads `<prefix>_summary.csv`, `<prefix>_position_probs.csv`, `<prefix>_standings_snapshot.csv`
and `<prefix>_metadata.json` for each league, plus the `cl_*` files for the Champions League.
"""

import argparse
import json
import re
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
AFFIXES = r"^(?:FC|AFC|CF|AC|ACF|AS|SS|SSC|US|SC|SV|RC|RCD|CA|UD|SD|OGC|AJ|ES|BC|FK|SK|ŠK|VfB|VfL|1\.)\s+|\s+(?:FC|AFC|CF|CFC|BC|OSC|SCO|AC|UD|FK|SK|KV|Calcio|\d{4}|\d{2})$"


def short_name(name):
    if name in SHORT_NAMES:
        return SHORT_NAMES[name]
    previous = None
    while previous != name:
        previous, name = name, re.sub(AFFIXES, "", name).strip()
    return name


def num(value, digits=2):
    return round(float(value), digits)


def zone_probabilities(row, zones):
    return {key: num(sum(row[str(p)] for p in range(first, last + 1))) for key, _, first, last in zones}


def zones_json(zones):
    return [{"key": key, "label": label, "from": first, "to": last} for key, label, first, last in zones]


def export_league(src, slug, code, name, country, zones):
    prefix = code.lower()
    summary = pd.read_csv(src / f"{prefix}_summary.csv", index_col=0)
    probs = pd.read_csv(src / f"{prefix}_position_probs.csv", index_col=0)
    standings = pd.read_csv(src / f"{prefix}_standings_snapshot.csv").set_index("team")
    meta = json.loads((src / f"{prefix}_metadata.json").read_text())
    teams = []
    for team in summary.sort_values(["expected_position", "expected_points"], ascending=[True, False]).index:
        row, now = summary.loc[team], standings.loc[team]
        teams.append({
            "name": short_name(team), "full": team,
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
    }


def export_ucl(src):
    forecast = json.loads((src / "cl_forecast.json").read_text())
    meta = json.loads((src / "cl_metadata.json").read_text())
    standings = pd.read_csv(src / "cl_standings_snapshot.csv").set_index("team")
    names = meta["data"]["display_names"]
    label = lambda key: short_name(names.get(key, key.title()))
    summary = pd.DataFrame(forecast["summary"]).T
    teams = []
    for key in summary.sort_values(["expected_position", "expected_points"], ascending=[True, False]).index:
        row, now = summary.loc[key], standings.loc[key]
        probs = forecast["position_probabilities_pct"][key]
        teams.append({
            "key": key, "name": label(key), "full": names.get(key, key),
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
        "bracket": {"stages": stages, "champion": label(bracket["champion"]), "note": bracket["draw_label"]},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--src", type=Path, default=Path("out/site"))
    parser.add_argument("--dest", type=Path, default=Path("site/data"))
    args = parser.parse_args(argv)
    args.dest.mkdir(parents=True, exist_ok=True)
    exports = [export_league(args.src, *league) for league in LEAGUES] + [export_ucl(args.src)]
    for data in exports:
        (args.dest / f"{data['slug']}.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")
    index = [{key: data[key] for key in ("slug", "code", "name", "country", "season", "generated_at")} for data in exports]
    (args.dest / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n")
    print(f"Wrote {len(exports)} competitions to {args.dest}")


if __name__ == "__main__":
    main()
