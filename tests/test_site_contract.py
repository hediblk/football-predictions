import copy
import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

from standing_prediction import site_history


ROOT = Path(__file__).resolve().parents[1]
ZONES = [("ucl", "Top one", 1, 1), ("europe", "Europe", 2, 2), ("releg", "Relegation", 3, 3)]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILD = script("build_site_data")
CONTRACT = script("validate_site_data")


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def write_ucl_outputs(path):
    keys = [f"club-{i:02}" for i in range(1, 37)]
    names = {key: f"Club Number{i:02} FC" for i, key in enumerate(keys, 1)}
    summary = {key: {
        "expected_position": 18.5, "expected_points": 10.26, "points_p10": 5.9, "points_p90": 15.1,
        "top8_pct": 800 / 36, "playoffs_pct": 1600 / 36, "eliminated_pct": 1200 / 36,
        "round16_pct": 1600 / 36, "quarterfinal_pct": 800 / 36,
        "semifinal_pct": 400 / 36, "final_pct": 200 / 36, "title_pct": 100 / 36,
    } for key in keys}
    summary[keys[0]]["title_pct"] = 5
    summary[keys[1]]["title_pct"] = 100 - 5 - 34 * 100 / 36
    stages = {}
    pairs = {"playoffs": (range(8, 16), range(16, 24)), "round16": (range(8), range(8, 16)),
             "quarterfinal": (range(4), range(4, 8)), "semifinal": (range(2), range(2, 4)),
             "final": ([0], [1])}
    for stage, (first, second) in pairs.items():
        stages[stage] = [{"team1": keys[a], "team2": keys[b],
                          "winner": keys[b] if stage == "final" else keys[a],
                          "advance_probability": 61.24, "observed": False} for a, b in zip(first, second)]
    write_json(path / "cl_forecast.json", {
        "summary": summary,
        "position_probabilities_pct": {key: {str(p): 100 / 36 for p in range(1, 37)} for key in keys},
        "bracket": {"stages": stages, "champion": keys[1], "draw_label": "Illustrative draw",
                    "projected_league_order": keys},
    })
    write_json(path / "cl_metadata.json", {
        "season": 2026, "generated_at": "2026-10-13T05:35:00+00:00", "as_of": "2026-10-13T05:30:00+00:00",
        "data_cutoff": None, "n_sim": 1000, "data": {"display_names": names},
        "league_validation": {"finished": 18, "remaining": 126},
    })
    pd.DataFrame([{"team": key, "position": i, "played": 1, "points": 0, "goal_diff": 0}
                  for i, key in enumerate(keys, 1)]).to_csv(path / "cl_standings_snapshot.csv", index=False)
    pd.DataFrame([{"homeTeam": key, "homeTeamId": 1000 + i, "awayTeam": keys[i % 36],
                   "awayTeamId": 1000 + i % 36 + 1} for i, key in enumerate(keys, 1)]).to_csv(
        path / "cl_matches_snapshot.csv", index=False)


@pytest.fixture
def exported(tmp_path):
    raw = json.loads((ROOT / "tests/fixtures/site_export.json").read_text())
    inputs = tmp_path / "outputs"
    inputs.mkdir()
    for name, key in (("summary", "summary"), ("position_probs", "position_probs")):
        pd.DataFrame(raw[key]).set_index("team").to_csv(inputs / f"pl_{name}.csv")
    pd.DataFrame(raw["standings"]).to_csv(inputs / "pl_standings_snapshot.csv", index=False)
    pd.DataFrame(raw["matches"]["matches"]).to_csv(inputs / "pl_matches_snapshot.csv", index=False)
    write_json(inputs / "pl_metadata.json", raw["metadata"])
    write_json(inputs / "pl_match_forecasts.json", raw["matches"])
    write_json(inputs / "pl_stakes.json", raw["stakes"])
    write_ucl_outputs(inputs)
    pd.DataFrame(raw["ratings"]).to_csv(inputs / "cl_club_ratings.csv", index=False)
    league = BUILD.export_league(inputs, "premier-league", "PL", "Premier League", "England", ZONES)
    ucl = BUILD.export_ucl(inputs)
    leagues = [league] + [{"slug": slug, "teams": []} for slug in CONTRACT.COMPETITIONS
                         if slug not in ("premier-league", "champions-league")]
    clubs = BUILD.export_clubs(inputs, leagues, ucl)
    return {"league": league, "ucl": ucl, "matches": BUILD.export_matches(inputs, "premier-league", "pl"),
            "clubs": clubs, "inputs": inputs}


def test_domestic_export_preserves_known_values_and_units(exported):
    data = exported["league"]
    CONTRACT.validate_payload(data, "league")
    assert [team["name"] for team in data["teams"]] == ["Alpha", "Bravo", "Charlie"]
    alpha, _, charlie = data["teams"]
    assert {key: alpha[key] for key in ("id", "position", "xpts", "xpos", "probs", "title", "ucl", "europe", "releg")} == {
        "id": 57, "position": 2, "xpts": 12.3, "xpos": 1.5, "probs": [60, 30, 10],
        "title": 60, "ucl": 60, "europe": 30, "releg": 10,
    }
    assert charlie["id"] is None and charlie["points"] == -6 and charlie["xpts"] == -2.4
    assert data["data_cutoff"] is None and data["fixture_notes"][0]["score"] == "0-2"


def test_ucl_export_distinguishes_direct_entry_and_progression(exported):
    data = exported["ucl"]
    CONTRACT.validate_payload(data, "ucl")
    first = data["teams"][0]
    assert {key: first[key] for key in ("key", "id", "name", "xpts", "p10", "p90", "r16", "playoff", "out", "title")} == {
        "key": "club-01", "id": 1001, "name": "Club Number01", "xpts": 10.3,
        "p10": 5, "p90": 15, "r16": 22.22, "playoff": 44.44, "out": 33.33, "title": 5,
    }
    assert first["stages"] == {"round16": 44.44, "quarterfinal": 22.22, "semifinal": 11.11, "final": 5.56}
    assert first["probs"] == [2.78] * 36
    assert data["data_cutoff"] == "2026-10-13T05:30:00+00:00"
    assert data["bracket"]["champion"] == "Club Number02"
    assert data["bracket"]["stages"]["final"][0]["advance"] == 61.2
    assert len(data["bracket"]["seeds"]) == 24


def test_match_export_checks_known_tuple_direction_and_precision(exported):
    data = exported["matches"]
    CONTRACT.validate_payload(data, "matches")
    assert [match["id"] for match in data["matches"]] == [2, 1]
    upcoming, played = data["matches"]
    assert played["p"] == [0.55, 0.25, 0.2]
    assert played["score"] == [0, 2] and played["xg"] == [1.23, 0.46]
    assert played["exp"] == [1.61, 0.98] and played["call"] == [2, 1, 0.13]
    assert played["top"][0] == [2, 1, 0.13] and played["p_score"] == 0.0346
    assert (played["btts"], played["o25"]) == (0.532, 0.613)
    assert upcoming["reported"] == "CANCELLED" and upcoming["md"] is None
    assert upcoming["stakes"] == {"n": [100, 500, 400], "teams": [
        {"id": 57, "name": "Alpha", "title": [None, 60, 20]},
        {"id": None, "name": "Charlie", "releg": [None, 30, 50]},
    ]}


def test_club_export_uses_reference_scale_and_independent_ranks(exported):
    data = exported["clubs"]
    CONTRACT.validate_payload(data, "clubs")
    first, second, _ = data["clubs"]
    assert (first["rating"], first["attack"], first["gf"], first["ga"]) == (70, 75.1, 2.35, 1.13)
    assert (first["rating_rank"], first["defense_rank"], second["defense_rank"]) == (1, 2, 1)
    assert data["featured"] == [65, 57] and data["league_averages"]["premier-league"] == 56.7


@pytest.fixture
def dataset(tmp_path, exported):
    dest = tmp_path / "site/data"
    competitions = []
    for slug, code in CONTRACT.COMPETITIONS.items():
        data = copy.deepcopy(exported["ucl"] if code == "CL" else exported["league"])
        data.update(slug=slug, code=code)
        competitions.append(data)
        write_json(dest / f"{slug}.json", data)
    write_json(dest / "index.json", [{key: data[key] for key in CONTRACT.INDEX_FIELDS} for data in competitions])
    write_json(dest / "clubs.json", exported["clubs"])
    write_json(dest / "matches/premier-league.json", exported["matches"])
    BUILD.update_history(dest, [exported["league"], exported["ucl"]], {57: (70.04, 75.06, 65.02), 1001: (40, 42, 38)})
    write_json(dest / "crests.json", {"57": {"name": "Alpha", "source": "https://example.org/57.svg",
                                             "path": "assets/crests/57.svg"}})
    crest = dest.parent / "assets/crests/57.svg"
    crest.parent.mkdir(parents=True)
    crest.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"/>')
    return dest


def test_complete_exported_dataset_and_history(dataset):
    assert CONTRACT.validate_site_data(dataset) == 14
    history = json.loads((dataset / "history/2026/premier-league.json").read_text())
    assert history["teams"][2]["id"] == "charlie" and history["teams"][0]["title"] == [60]
    ucl_history = json.loads((dataset / "history/2026/champions-league.json").read_text())
    assert [ucl_history["teams"][0][key][0] for key in ucl_history["metrics"]] == [22, 67, 44, 22, 11, 5.6, 5]
    weekly = json.loads((dataset / "history/2026/clubs.json").read_text())
    assert weekly["weeks"][0]["date"] == "2026-10-12" and weekly["weeks"][0]["clubs"]["57"] == [70, 75.1, 65]


def test_retained_files_optional_absence_and_old_history_are_valid(dataset):
    for path in (dataset / "matches").glob("*.json"):
        path.unlink()
    (dataset / "crests.json").unlink()
    table = json.loads((dataset / "la-liga.json").read_text())
    table.update(season="2025/26", generated_at="2025-10-12T05:30:00Z", as_of="2025-10-12T05:30:00Z")
    table["extra_compatible_field"] = True
    write_json(dataset / "la-liga.json", table)
    index = json.loads((dataset / "index.json").read_text())
    next(row for row in index if row["slug"] == "la-liga").update(season=table["season"], generated_at=table["generated_at"])
    write_json(dataset / "index.json", index)
    old = {"slug": "la-liga", "season": "2025/26", "metrics": ["title", "ucl", "releg"],
           "dates": ["2025-08-20", "2025-08-30"], "cutoff": None,
           "teams": [{"id": "departed-club", "name": "Departed club", "title": [None, 1.2],
                      "ucl": [None, 10], "releg": [None, 0]}]}
    write_json(dataset / "history/2025/la-liga.json", old)
    assert CONTRACT.validate_site_data(dataset) == 13


@pytest.mark.parametrize("family,change,message", [
    ("league", lambda d: d["teams"][0].pop("xpts"), "required property"),
    ("league", lambda d: d["teams"][0].update(xpts=float("nan")), "nonfinite"),
    ("league", lambda d: d["teams"][1].update(id=57), "duplicate id"),
    ("league", lambda d: d["teams"][0].update(probs=[60, 40]), "vector length"),
    ("league", lambda d: d["teams"][0].update(probs=[50, 30, 10]), "probability sum"),
    ("league", lambda d: d["teams"][0].update(ucl=20), "position band"),
    ("league", lambda d: d["teams"][0].update(xpos=2.5), "expected position"),
    ("league", lambda d: d.update(generated_at="not-a-timestamp"), "date-time"),
    ("league", lambda d: d.update(as_of="2026-10-13T05:30:00"), "date-time"),
    ("league", lambda d: d.update(as_of="2026-02-30T05:30:00Z"), "date-time"),
    ("ucl", lambda d: d["teams"][1].update(key="club-01"), "duplicate key"),
    ("ucl", lambda d: d["teams"][0]["stages"].update(final=20), "not nested"),
    ("ucl", lambda d: d["bracket"].update(champion="Club Number01"), "champion differs"),
    ("matches", lambda d: d["matches"][1].update(p=[55, 25, 20]), "greater than"),
    ("matches", lambda d: d["matches"][1].update(p=[0.4, 0.4, 0.4]), "probability sum"),
    ("matches", lambda d: d["matches"][1].update(score=[0, 2, 3]), "too long"),
    ("matches", lambda d: d["matches"][1].update(away_id=57), "plays itself"),
    ("matches", lambda d: d["matches"][1].update(id=None), "integer"),
    ("matches", lambda d: d["matches"][1].pop("exp"), "required property"),
    ("clubs", lambda d: d["clubs"][0].update(rating_rank=2), "rank sequence"),
])
def test_invalid_payloads_fail(exported, family, change, message):
    data = copy.deepcopy(exported[family])
    change(data)
    with pytest.raises(ValueError, match=message):
        CONTRACT.validate_payload(data, family)


def test_absent_forecast_and_older_optional_fields_are_valid(exported):
    data = copy.deepcopy(exported["matches"])
    data["rule"] = None
    for field in ("p", "exp", "top", "btts", "o25", "at", "call", "stakes"):
        data["matches"][0].pop(field, None)
    data["matches"][1].pop("call")
    CONTRACT.validate_payload(data, "matches")


def test_position_column_conservation_is_checked_independently(exported):
    data = copy.deepcopy(exported["league"])
    data["teams"][0].update(probs=[60, 20, 20], europe=20, releg=20, xpos=1.6)
    with pytest.raises(ValueError, match="column probability sum"):
        CONTRACT.validate_payload(data, "league")


def test_match_sum_allows_serialization_rounding(exported):
    data = copy.deepcopy(exported["matches"])
    data["matches"][0]["p"] = [0.3333, 0.3333, 0.3333]
    CONTRACT.validate_payload(data, "matches")


@pytest.mark.parametrize("change,message", [
    (lambda d: d["teams"][0].update(title=[]), "series length"),
    (lambda d: d.update(metrics=["top8", "top24", "last16", "qf", "sf", "final", "title"]), "was expected"),
    (lambda d: d.update(dates=["2026-10-13", "2026-10-12"]), "strictly increase"),
])
def test_history_rejects_wrong_lengths_metrics_and_date_order(dataset, change, message):
    data = json.loads((dataset / "history/2026/premier-league.json").read_text())
    change(data)
    with pytest.raises(ValueError, match=message):
        CONTRACT.validate_payload(data, "history")


@pytest.mark.parametrize("path,change,message", [
    ("index.json", lambda d: d[0].update(generated_at="2020-01-01T00:00:00Z"), "metadata differs"),
    ("index.json", lambda d: d.pop(), "competition set"),
    ("crests.json", lambda d: d["57"].update(path="assets/crests/absent.svg"), "missing asset"),
    ("crests.json", lambda d: d["57"].update(source="not-a-uri"), "uri"),
    ("history/2026/clubs.json", lambda d: d["weeks"][0].update(date="2026-10-13"), "Monday"),
])
def test_invalid_dataset_references_fail(dataset, path, change, message):
    data = json.loads((dataset / path).read_text())
    change(data)
    write_json(dataset / path, data)
    with pytest.raises(ValueError, match=message):
        CONTRACT.validate_site_data(dataset)


def test_unknown_files_nonfinite_json_and_required_absence_fail(dataset):
    write_json(dataset / "unrecognized.json", {})
    (dataset / "clubs.json").write_text('{"bad": NaN}')
    (dataset / "serie-a.json").unlink()
    with pytest.raises(ValueError) as error:
        CONTRACT.validate_site_data(dataset)
    assert "unknown JSON file family" in str(error.value)
    assert "nonfinite JSON number" in str(error.value)
    assert "serie-a.json: required valid file missing" in str(error.value)


def test_published_data_satisfies_contract():
    assert CONTRACT.validate_site_data(ROOT / "site/data") >= 8
