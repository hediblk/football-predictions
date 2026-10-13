import contextlib
from functools import wraps
import hashlib
import importlib.metadata
import inspect
import io
import json
from pathlib import Path
import platform
import shlex
import socket
import subprocess
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import requests

from champions_league import cli as ucl_cli, coefficients, report, strengths, tournament
from champions_league.data import UCLInputs
from standing_prediction import defaults, predict_positions as domestic
from standing_prediction.data import standings_from_matches
from standing_prediction.match_forecasts import scoreline_distribution
from standing_prediction.odds import match_odds


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "numerical"
SEED, N_SIM = 7, 10000
DEPENDENCIES = ("numpy", "pandas", "scipy", "scikit-learn")


def frame(rows):
    result = pd.DataFrame(rows)
    for column in ("utcDate", "available_at"):
        if column in result:
            result[column] = pd.to_datetime(result[column], utc=True)
    return result


def load_case(name):
    data = json.loads((FIXTURES / f"{name}.json").read_text())
    data["history"], data["fixtures"] = frame(data["history"]), frame(data["fixtures"])
    return data


def forbid_network(*args, **kwargs):
    pytest.fail("Numerical regressions must not access the network")


def cli_options(module, command):
    captured = {}
    fake = SimpleNamespace(summary=pd.DataFrame({"title_pct": [100]}, index=["A"]), metadata={"data": {}})
    with pytest.MonkeyPatch.context() as patch, contextlib.redirect_stdout(io.StringIO()):
        patch.setattr(module, "run_prediction" if module is domestic else "run_forecast",
                      lambda **kwargs: (captured.update(kwargs), fake)[1])
        patch.setattr(module, "load_dotenv", lambda: None)
        module.main(command)
    keys = ("n_sim", "seed", "max_goals", "xi", "lambda_reg", "prior_seasons", "use_odds", "weights",
            "calibrate", "xg_weight", "xg_scale", "h2h_weight", "odds_snapshot", "odds_archive",
            "match_forecasts", "sensitivity")
    return {key: str(value) if isinstance(value, Path) else value
            for key, value in captured.items() if key in keys}


def effective_configuration():
    settings = {"calibration_version": defaults.CALIBRATION_VERSION,
                "calibration_sha256": hashlib.sha256(Path(defaults.__file__).with_name("calibrated_weights.json").read_bytes()).hexdigest(),
                "fit": defaults.DEFAULT_FIT, "weights": defaults.DEFAULT_WEIGHTS,
                "no_odds_weights": {key: defaults.DEFAULT_WEIGHTS[key] / (1 - defaults.DEFAULT_WEIGHTS["odds"])
                                    for key in ("main", "elo")},
                "xg_weight": defaults.DEFAULT_XG_WEIGHT, "xg_scale": defaults.DEFAULT_XG_SCALE,
                "ucl": {"offset_ridge": strengths.DEFAULT_OFFSET_RIDGE, "club_ridge": strengths.DEFAULT_CLUB_RIDGE,
                        "market_weight": strengths.DEFAULT_MARKET_WEIGHT, "shift_ridge": strengths.DEFAULT_SHIFT_RIDGE},
                "cli_domestic": cli_options(domestic, []), "cli_ucl": cli_options(ucl_cli, [])}
    script = (ROOT / "scripts" / "refresh_site.sh").read_text()
    for command, module, key in (("football-predict", domestic, "daily_domestic"), ("football-ucl", ucl_cli, "daily_ucl")):
        line = next(line for line in script.splitlines() if command + " " in line and not line.lstrip().startswith("#"))
        arguments = line.partition(command + " ")[2].split("||", 1)[0].split("; then", 1)[0]
        tokens = shlex.split(arguments)
        replacements = {"$competition": "PL", "$N_SIM": str(N_SIM), "$OUT": "out/site"}
        settings[key] = cli_options(module, [replacements.get(token, token) for token in tokens])
    assert settings["daily_domestic"]["use_odds"] is False
    assert settings["daily_ucl"]["odds_snapshot"] is None
    assert settings["daily_ucl"]["odds_archive"] == "data/odds"
    for function in (domestic.run_prediction, domestic.fit_prediction_models, ucl_cli.run_forecast, strengths.fit_strengths):
        settings[function.__module__ + "." + function.__name__] = {
            key: parameter.default for key, parameter in inspect.signature(function).parameters.items()
            if key in ("xi", "lambda_reg", "prior_seasons", "xg_weight", "xg_scale", "h2h_weight", "calibrate",
                       "offset_ridge", "club_ridge", "market_weight", "shift_ridge")}
    return settings


def provenance(name):
    return {"generating_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "python": platform.python_version(), "platform": platform.platform(),
            "dependencies": {name: importlib.metadata.version(name) for name in DEPENDENCIES},
            "input_sha256": hashlib.sha256((FIXTURES / f"{name}.json").read_bytes()).hexdigest(),
            "seed": SEED, "n_sim": N_SIM}


def run_case(name, out_dir, patch):
    data = load_case(name)
    fixtures, history, teams = data["fixtures"], data["history"], data["teams"]
    table = standings_from_matches(fixtures, teams=teams, competition="PL")
    models = []
    patch.setattr(requests.sessions.Session, "request", forbid_network)
    patch.setattr(socket.socket, "connect", forbid_network)
    patch.setattr(socket, "create_connection", forbid_network)
    out_dir.mkdir(parents=True, exist_ok=True)
    if name == "domestic":
        original = domestic.fit_prediction_models

        @wraps(original)
        def fit(*args, **kwargs):
            model = original(*args, **kwargs)
            if not models:
                models.append(model)
            return model

        patch.setattr(domestic, "fit_prediction_models", fit)
        patch.setattr(domestic, "fetch_matches", lambda *args, **kwargs: fixtures.copy())
        patch.setattr(domestic, "fetch_standings", lambda *args, **kwargs: table.copy())
        patch.setattr(domestic, "load_history", lambda *args, **kwargs: history.copy())
        patch.setattr(domestic, "load_season_xg", lambda matches, **kwargs: matches.copy())
        patch.setattr(domestic, "_write_html", lambda *args, **kwargs: None)
        odds_path = out_dir / "frozen_odds.csv"
        pd.DataFrame(data["odds"]).to_csv(odds_path, index=False)
        result = domestic.run_prediction(competition="PL", season=data["season"], as_of=data["origin"],
                                         n_sim=N_SIM, seed=SEED, out_dir=out_dir, odds_snapshot=odds_path, client=object())
        forecasts = json.loads((out_dir / "pl_match_forecasts.json").read_text())["matches"]
        model = models[0][0]
        fitting = {key: result.metadata[key] for key in ("xi", "lambda_reg", "weights", "xg_weight", "xg_scale",
                                                        "h2h_weight", "calibrated", "odds_matched")}
        assert 0 < result.metadata["odds_matched"] < result.metadata["remaining_fixtures"]
    else:
        original = strengths.fit_strengths

        @wraps(original)
        def fit(*args, **kwargs):
            model = original(*args, **kwargs)
            if not models:
                models.append(model)
            return model

        patch.setattr(strengths, "fit_strengths", fit)
        patch.setattr(coefficients, "fetch_coefficients", lambda *args, **kwargs: (data["coefficients"], {"complete": True}))
        from champions_league import data as ucl_data
        patch.setattr(ucl_data, "load_market_quotes", lambda *args, **kwargs: pd.DataFrame(data["market"]))
        patch.setattr(report, "write_report", lambda *args, **kwargs: None)
        inputs = UCLInputs(fixtures.copy(), table, history.copy(), data["team_leagues"], pd.DataFrame(),
                           {"display_names": {team: team for team in teams}})
        result = ucl_cli.run_forecast(season=data["season"], as_of=data["origin"], n_sim=N_SIM, seed=SEED,
                                     out_dir=out_dir, inputs=inputs)
        forecasts = json.loads((out_dir / "cl_match_forecasts.json").read_text())["matches"]
        model = models[0]
        fitting = {key: result.metadata[key] for key in ("fit_settings", "weights", "xg_weight", "xg_scale", "h2h_weight")}
        fitting["market_quotes"] = model.metadata["market_quotes"]
        fitting["joint_fit"] = {key: model.metadata[key] for key in
                                ("xi", "lambda_reg", "offset_ridge", "offset_prior", "club_ridge", "market_weight", "shift_ridge")}
        fitting["xg"] = {key: model.metadata["xg"][key] for key in ("weight", "scale", "matches")}
        assert fitting["market_quotes"] > 0
        assert result.metadata["quoted_fixtures"] == 0
    match_fields = ("p_home", "p_draw", "p_away", "exp_home_goals", "exp_away_goals", "btts", "over_2_5")
    match_values = {str(row["id"]): {key: row[key] for key in match_fields} for row in forecasts}
    selected = [row for row in forecasts if row["status"] != "FINISHED"][:2]
    distributions, rates = {}, {}
    for row in selected:
        _, matrix = model.score_matrix(row["homeTeam"], row["awayTeam"])
        distribution = scoreline_distribution(matrix, [row[key] for key in ("p_home", "p_draw", "p_away")])
        distributions[str(row["id"])] = distribution.tolist()
        rates[str(row["id"])] = list(model.expected_goals(row["homeTeam"], row["awayTeam"]))
    payload = {"configuration": effective_configuration(), "fitting": fitting, "matches": match_values,
               "rates": rates, "distributions": distributions,
               "positions": result.probabilities.to_dict(orient="index"),
               "summary": result.summary.to_dict(orient="index")}
    return {"payload": payload, "result": result, "data": data, "model": models[0], "table": table}


@pytest.fixture(scope="module", params=("domestic", "ucl"))
def regression(request, tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        actual = run_case(request.param, tmp_path_factory.mktemp(request.param), patch)
        yield request.param, actual


def close(actual, expected, tolerance, label):
    actual, expected = np.asarray(actual, dtype=float), np.asarray(expected, dtype=float)
    assert actual.shape == expected.shape, label
    assert np.isfinite(actual).all(), label
    difference = np.abs(actual - expected)
    assert difference.max(initial=0) <= tolerance, f"{label}: maximum absolute difference {difference.max():.8g} > {tolerance}"


def test_frozen_forecast_matches_reviewed_baseline(regression):
    name, actual = regression
    baseline = json.loads((FIXTURES / f"{name}_baseline.json").read_text())
    metadata, expected, current = baseline["provenance"], baseline["payload"], actual["payload"]
    assert metadata["input_sha256"] == provenance(name)["input_sha256"]
    assert metadata["dependencies"] == provenance(name)["dependencies"]
    assert current["configuration"] == expected["configuration"]
    assert current["fitting"] == expected["fitting"]
    for category, tolerance in (("matches", 1e-6), ("rates", 1e-5), ("distributions", 1e-6), ("positions", .1)):
        assert current[category].keys() == expected[category].keys(), category
        for key, value in current[category].items():
            wanted = expected[category][key]
            if isinstance(value, dict):
                value = {str(field): number for field, number in value.items()}
                assert value.keys() == wanted.keys(), f"{name}/{category}/{key} labels"
                for field, number in value.items():
                    limit = 1e-5 if category == "matches" and field in ("exp_home_goals", "exp_away_goals") else tolerance
                    close(number, wanted[field], limit, f"{name}/{category}/{key}/{field}")
            else:
                close(value, wanted, tolerance, f"{name}/{category}/{key}")
    assert current["summary"].keys() == expected["summary"].keys()
    for team, row in current["summary"].items():
        assert row.keys() == expected["summary"][team].keys(), f"{name}/summary/{team} metrics"
        for metric, value in row.items():
            if metric.startswith("points_p"):
                continue
            close(value, expected["summary"][team][metric], .1 if metric.endswith("_pct") else .01,
                  f"{name}/summary/{team}/{metric}")


def test_forecast_conserves_probabilities_and_feasible_points(regression):
    name, actual = regression
    result, table = actual["result"], actual["table"].set_index("team")
    probabilities, summary = result.probabilities, result.summary
    assert np.isfinite(probabilities).all().all() and probabilities.ge(0).all().all() and probabilities.le(100).all().all()
    close(probabilities.sum(axis=0), np.full(len(table), 100), 1e-9, "one club per position")
    close(probabilities.sum(axis=1), np.full(len(table), 100), 1e-9, "one position per club")
    expected_position = probabilities @ np.arange(1, len(table) + 1) / 100
    close(summary["expected_position"], expected_position.reindex(summary.index), 5.1e-5, "expected position")
    if name == "domestic":
        close(summary["title_pct"], probabilities[1].reindex(summary.index), 5.1e-5, "title equals first place")
    remaining = actual["data"]["fixtures"].query("status != 'FINISHED'")
    games_left = pd.concat([remaining.homeTeam, remaining.awayTeam]).value_counts().reindex(summary.index, fill_value=0)
    points_now = table.points.reindex(summary.index)
    assert summary.points_p10.le(summary.points_p90).all()
    for column in ("expected_points", "points_p10", "points_p90"):
        assert np.isfinite(summary[column]).all()
        assert summary[column].ge(points_now).all() and summary[column].le(points_now + 3 * games_left).all()
    for fixture, row in actual["payload"]["matches"].items():
        p = np.array([row[key] for key in ("p_home", "p_draw", "p_away")])
        assert ((p >= 0) & (p <= 1)).all()
        close(p.sum(), 1, 1e-12, f"match {fixture} outcomes")
    for fixture, values in actual["payload"]["distributions"].items():
        matrix = np.array(values)
        assert np.isfinite(matrix).all() and (matrix >= 0).all()
        close(matrix.sum(), 1, 1e-12, "scoreline normalization")
        home, away = np.indices(matrix.shape)
        row = actual["payload"]["matches"][fixture]
        close([matrix[mask].sum() for mask in (home > away, home == away, home < away)],
              [row[key] for key in ("p_home", "p_draw", "p_away")], 1e-12, "blended outcome masses")
    assert all(np.isfinite(rates).all() and (np.asarray(rates) > 0).all()
               for rates in actual["payload"]["rates"].values())
    if name == "ucl":
        totals = {"top8": 8, "playoffs": 16, "eliminated": 12, "round16": 16, "quarterfinal": 8,
                  "semifinal": 4, "final": 2, "title": 1}
        for stage, count in totals.items():
            close(summary[f"{stage}_pct"].sum(), count * 100, 1e-9, stage)
        close(summary[["top8_pct", "playoffs_pct", "eliminated_pct"]].sum(axis=1), np.full(36, 100), 1e-9, "qualification partition")
        progression = summary[[f"{stage}_pct" for stage in ("title", "final", "semifinal", "quarterfinal", "round16")]]
        assert (np.diff(progression, axis=1) >= -1e-9).all()
        assert summary.round16_pct.le(summary.top8_pct + summary.playoffs_pct + 1e-9).all()
        assert summary.top8_pct.le(summary.round16_pct + 1e-9).all()
        orders = result.league_orders
        assert np.array_equal(np.sort(orders, axis=1), np.broadcast_to(np.arange(36), orders.shape))


def test_excluded_future_information_cannot_move_the_fit(regression):
    name, actual = regression
    data = actual["data"]
    origin = pd.Timestamp(data["origin"])
    history = data["history"].copy()
    future = history.iloc[:1].copy()
    future["utcDate"] = origin
    future[["homeGoals", "awayGoals", "home_xg", "away_xg"]] = [20, 0, 20, 0]
    changed = pd.concat([history, future], ignore_index=True)
    if name == "domestic":
        played = data["fixtures"].query("status == 'FINISHED'")
        before = domestic.fit_prediction_models(played, teams=data["teams"], history=history, reference_date=origin)[0]
        after = domestic.fit_prediction_models(played, teams=data["teams"], history=changed, reference_date=origin)[0]
        history.loc[0, "homeGoals"] += 8
        eligible = domestic.fit_prediction_models(played, teams=data["teams"], history=history, reference_date=origin)[0]
    else:
        market = pd.DataFrame(data["market"])
        future["utcDate"], future["available_at"] = origin - pd.Timedelta(hours=1), origin
        changed = pd.concat([changed, future], ignore_index=True)
        invalid_quote = market.iloc[:1].assign(observed_at=origin.isoformat(), p_home=.9, p_draw=.05, p_away=.05)
        before = strengths.fit_strengths(history, teams=data["teams"], team_leagues=data["team_leagues"], as_of=origin, market=market)
        after = strengths.fit_strengths(changed, teams=data["teams"], team_leagues=data["team_leagues"], as_of=origin,
                                       market=pd.concat([market, invalid_quote], ignore_index=True))
        market.loc[0, ["p_home", "p_draw", "p_away"]] = [.8, .1, .1]
        eligible = strengths.fit_strengths(history, teams=data["teams"], team_leagues=data["team_leagues"], as_of=origin, market=market)
    pair = data["teams"][:2]
    close(after.match_outcome_probs(*pair), before.match_outcome_probs(*pair), 1e-12, "future result/quote leakage")
    assert np.max(np.abs(np.array(eligible.match_outcome_probs(*pair)) - before.match_outcome_probs(*pair))) > 1e-6


def test_same_inputs_repeat_exactly(regression, tmp_path):
    name, actual = regression
    with pytest.MonkeyPatch.context() as patch:
        repeated = run_case(name, tmp_path, patch)["payload"]
    assert repeated == actual["payload"]


def test_domestic_quotes_respect_origin_and_kickoff():
    data = load_case("domestic")
    odds, origin = pd.DataFrame(data["odds"]), pd.Timestamp(data["origin"])
    expected = match_odds(data["fixtures"], odds, as_of=origin)
    changed = odds.iloc[:1].assign(observed_at=(origin + pd.Timedelta(seconds=1)).isoformat(),
                                  p_home_book=.9, p_draw_book=.05, p_away_book=.05)
    assert match_odds(data["fixtures"], pd.concat([odds, changed]), as_of=origin) == expected
    changed["observed_at"] = origin.isoformat()
    assert match_odds(data["fixtures"], pd.concat([odds, changed]), as_of=origin) != expected
    kickoff = pd.Timestamp(changed.iloc[0].commence_time)
    changed["observed_at"] = kickoff.isoformat()
    assert match_odds(data["fixtures"], pd.concat([odds, changed]), as_of=kickoff + pd.Timedelta(hours=1)) == expected


def test_ucl_played_match_refit_masks_unpublished_xg(monkeypatch):
    from champions_league import match_forecasts
    data = load_case("ucl")
    recent = data["history"].iloc[:2].copy()
    recent["utcDate"] = pd.to_datetime(["2026-08-30T15:00Z", "2026-08-31T15:00Z"])
    recent[["home_xg", "away_xg"]] = [4.0, 3.0]
    fixture = data["fixtures"].iloc[:1].copy()
    fixture["utcDate"] = pd.Timestamp("2026-09-01T15:00Z")
    captured = []
    monkeypatch.setattr(match_forecasts, "fit_strengths", lambda history, **kwargs: captured.append(history.copy()))
    monkeypatch.setattr(match_forecasts, "fixture_forecasts", lambda model, fixtures, origin: [{} for _ in range(len(fixtures))])
    inputs = SimpleNamespace(fixtures=fixture, history=recent, standings=pd.DataFrame({"team": data["teams"]}),
                             team_leagues=data["team_leagues"])
    match_forecasts.match_forecasts(inputs, None, origin=pd.Timestamp("2026-09-02T05:30Z"))
    assert captured[0].iloc[0][["home_xg", "away_xg"]].tolist() == [4.0, 3.0]
    assert captured[0].iloc[1][["home_xg", "away_xg"]].isna().all()
