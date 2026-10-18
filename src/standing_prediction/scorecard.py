import math
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from scipy.stats import poisson


MISS_KINDS = ("draw", "upset", "called", "missed_draw_call")
XG_VERDICTS = ("won", "level", "lost", "unknown")
GOAL_METRICS = ("predicted", "goals", "xg", "mae_goals", "mae_xg")


def valid_pair(pair):
    return pair is not None and len(pair) == 2 and all(
        value is not None and math.isfinite(value) and value >= 0 for value in pair)


def on_chances(xg):
    if not valid_pair(xg):
        return None
    k = np.arange(int(poisson.ppf(1 - 1e-15, max(xg))) + 1)
    home, away = (poisson.pmf(k, mean) for mean in xg)
    p = np.array([(home * poisson.cdf(k - 1, xg[1])).sum(),
                  (home * away).sum(), (away * poisson.cdf(k - 1, xg[0])).sum()])
    return (p / p.sum()).tolist()


def miss_breakdown(p, result, xg):
    call = max(range(3), key=lambda i: p[i])
    favourite = 0 if p[0] >= p[2] else 2
    kind = ("called" if call == result else "missed_draw_call" if call == 1
            else "draw" if result == 1 else "upset")
    verdict = "unknown"
    if valid_pair(xg):
        margin = (xg[0] - xg[1]) * (1 if favourite == 0 else -1)
        verdict = "level" if abs(margin) <= 0.5 + 1e-12 else "won" if margin > 0 else "lost"
    return {"kind": kind, "xg": verdict}


def scoring_forecast(match, original):
    if match.get("published"):
        return {"p": match.get("p"), "elo": match.get("elo"),
                "call": match.get("call", [])[:2], "exp": match.get("exp")}
    if "p_home" in original:
        return {"p": [original[key] for key in ("p_home", "p_draw", "p_away")],
                "elo": original.get("elo"), "call": original.get("pick_score", [])[:2],
                "exp": [original.get(key) for key in ("exp_home_goals", "exp_away_goals")]}
    return {"p": None}


def fixture_diagnostics(match, original):
    if match["status"] != "FINISHED":
        return {}
    xg = match.get("xg")
    p = scoring_forecast(match, original)["p"]
    home, away = match["score"]
    result = 0 if home > away else 1 if home == away else 2
    fields = {"miss": miss_breakdown(p, result, xg)} if p is not None else {}
    xg_p = on_chances(xg)
    if xg_p is not None:
        fields["xg_p"] = xg_p
    return fields


def miss_summary(rows):
    confusion = [[0] * 3 for _ in range(3)]
    kinds = {kind: {"xg": dict.fromkeys(XG_VERDICTS, 0)} for kind in MISS_KINDS}
    for row in rows:
        confusion[max(range(3), key=lambda i: row["p"][i])][row["result"]] += 1
        miss = miss_breakdown(row["p"], row["result"], row.get("xg"))
        kinds[miss["kind"]]["xg"][miss["xg"]] += 1
    covered = [row for row in rows if valid_pair(row.get("xg")) and valid_pair(row.get("exp"))]
    team_games = 2 * len(covered)
    goals = {"team_games": team_games}
    values = {"predicted": [v for row in covered for v in row["exp"]],
              "goals": [v for row in covered for v in row["score"]],
              "xg": [v for row in covered for v in row["xg"]]}
    for key in ("goals", "xg"):
        values[f"mae_{key}"] = [abs(p - v) for p, v in zip(values["predicted"], values[key])]
    goals.update({key: sum(values[key]) / team_games if team_games else None for key in GOAL_METRICS})
    xg_scored = {}
    chances = [(row, on_chances(row.get("xg"))) for row in rows]
    for key, field in (("model", "p"), ("elo", "elo"), ("frequency", "frequency")):
        sample = [(row, q) for row, q in chances if q is not None and row.get(field) is not None]
        n = len(sample)
        xg_scored[key] = {"n": n, "log_loss": sum(
            -sum(qi * math.log(max(pi, 1e-15)) for qi, pi in zip(q, row[field]))
            for row, q in sample) / n if n else None,
            "real_log_loss": sum(proper_scores(row[field], row["result"])["log_loss"]
                                 for row, _ in sample) / n if n else None}
    return {"confusion": confusion, "kinds": kinds, "goals": goals, "xg_scored": xg_scored,
            "outcomes": {"expected": [sum(row["p"][i] / sum(row["p"]) for row in rows) for i in range(3)],
                         "actual": [sum(line[i] for line in confusion) for i in range(3)]}}


def combine_misses(records):
    blocks = [row["misses"] for row in records]
    team_games = sum(block["goals"]["team_games"] for block in blocks)
    xg_scored = {}
    for key in ("model", "elo", "frequency"):
        samples = [block["xg_scored"][key] for block in blocks]
        n = sum(sample["n"] for sample in samples)
        xg_scored[key] = {"n": n, **{metric: sum(s[metric] * s["n"] for s in samples if s["n"]) / n if n else None
                                     for metric in ("log_loss", "real_log_loss")}}
    return {
        "confusion": [[sum(b["confusion"][i][j] for b in blocks) for j in range(3)] for i in range(3)],
        "outcomes": {key: [sum(b["outcomes"][key][i] for b in blocks) for i in range(3)]
                     for key in ("expected", "actual")},
        "kinds": {kind: {"xg": {v: sum(b["kinds"][kind]["xg"][v] for b in blocks) for v in XG_VERDICTS}}
                  for kind in MISS_KINDS},
        "goals": {"team_games": team_games, **{key: sum(b["goals"][key] * b["goals"]["team_games"]
                  for b in blocks if b["goals"]["team_games"]) / team_games if team_games else None for key in GOAL_METRICS}},
        "xg_scored": xg_scored,
    }


def frequency_baseline(frames, season):
    counts = [0, 0, 0]
    used = []
    cutoff = pd.Timestamp(year=season, month=7, day=1, tz="UTC")
    for year, frame in sorted(frames.items()):
        if not season - 5 <= year < season:
            continue
        games = frame.dropna(subset=["homeGoals", "awayGoals"])
        games = games[pd.to_datetime(games["utcDate"], utc=True).lt(cutoff)]
        if "available_at" in games:
            games = games[pd.to_datetime(games["available_at"], utc=True).lt(cutoff)]
        if "status" in games:
            games = games[games["status"].isin(["FINISHED", "AWARDED"])]
        if games.empty:
            continue
        used.append(year)
        for home, away in games[["homeGoals", "awayGoals"]].itertuples(index=False, name=None):
            counts[0 if home > away else 1 if home == away else 2] += 1
    n = sum(counts)
    return {"seasons": used, "requested_seasons": list(range(season - 5, season)), "n": n,
            "p": [count / n for count in counts] if len(used) == 5 and n else None}


def proper_scores(p, result):
    truth = [int(i == result) for i in range(3)]
    return {
        "log_loss": -math.log(max(p[result], 1e-15)),
        "brier": sum((prob - actual) ** 2 for prob, actual in zip(p, truth)),
        "rps": sum((sum(p[:i]) - sum(truth[:i])) ** 2 for i in (1, 2)) / 2,
    }


def score_summary(rows, field="p"):
    rows = [row for row in rows if row.get(field) is not None]
    n = len(rows)
    scores = [proper_scores(row[field], row["result"]) for row in rows]
    return {"n": n, **{key: sum(score[key] for score in scores) / n if n else None
                       for key in ("log_loss", "brier", "rps")}}


def calibration(rows):
    bins = [{"lo": i / 10, "hi": (i + 1) / 10, "n": 0, "probability": None, "observed": None}
            for i in range(10)]
    probabilities, hits = [0.0] * 10, [0] * 10
    for row in rows:
        for outcome, p in enumerate(row["p"]):
            i = min(9, int(p * 10))
            bins[i]["n"] += 1
            probabilities[i] += p
            hits[i] += outcome == row["result"]
    for i, cell in enumerate(bins):
        if cell["n"]:
            cell.update(probability=probabilities[i] / cell["n"], observed=hits[i] / cell["n"])
    return bins


def record(rows):
    bins = calibration(rows)
    weeks = sorted({row["week"] for row in rows})
    series = []
    for week in weeks:
        cumulative = [row for row in rows if row["week"] <= week]
        series.append({"week": week, "model": score_summary(cumulative),
                       **{key: score_summary(cumulative, key) for key in ("frequency", "elo")}})
    n = len(rows)
    return {
        "n": n, "n_published": sum(row["published"] for row in rows), "model": score_summary(rows),
        "baselines": {key: {**score_summary(rows, key), "model": score_summary(
            [row for row in rows if row.get(key) is not None])} for key in ("frequency", "elo")},
        "called": sum(max(range(3), key=lambda i: row["p"][i]) == row["result"] for row in rows),
        "exact": sum(row.get("call") == row["score"] for row in rows),
        "avg_chance_given": sum(row["p"][row["result"]] for row in rows) / n if n else None,
        "calibration": bins, "weekly": series, "market": None, "misses": miss_summary(rows),
    }


def scorecard_entry(rows):
    return {**record(rows), "published": record([row for row in rows if row["published"]]),
            "reconstructed": record([row for row in rows if not row["published"]])}


def combine_scores(scores):
    n = sum(score["n"] for score in scores)
    return {"n": n, **{key: sum(score[key] * score["n"] for score in scores if score["n"]) / n if n else None
                       for key in ("log_loss", "brier", "rps")}}


def combine_records(records):
    total = {key: sum(row[key] for row in records) for key in ("n", "n_published", "called", "exact")}
    total["model"] = combine_scores([row["model"] for row in records])
    total["baselines"] = {key: {**combine_scores([row["baselines"][key] for row in records]),
                                "model": combine_scores([row["baselines"][key]["model"] for row in records])}
                          for key in ("frequency", "elo")}
    n = total["n"]
    total["avg_chance_given"] = sum(row["avg_chance_given"] * row["n"] for row in records if row["n"]) / n if n else None
    total["calibration"] = []
    for i in range(10):
        cells = [row["calibration"][i] for row in records]
        count = sum(cell["n"] for cell in cells)
        total["calibration"].append({"lo": i / 10, "hi": (i + 1) / 10, "n": count,
            **{key: sum(cell[key] * cell["n"] for cell in cells if cell["n"]) / count if count else None
               for key in ("probability", "observed")}})
    total["weekly"] = []
    for week in sorted({point["week"] for row in records for point in row["weekly"]}):
        latest = [next((point for point in reversed(row["weekly"]) if point["week"] <= week), None) for row in records]
        total["weekly"].append({"week": week, **{key: combine_scores([point[key] for point in latest if point])
                                                for key in ("model", "frequency", "elo")}})
    total["market"] = None
    total["misses"] = combine_misses(records)
    return total


def combine_entries(entries):
    return {**combine_records(entries),
            **{key: combine_records([entry[key] for entry in entries]) for key in ("published", "reconstructed")}}


def scoring_rows(matches, raw, frequency):
    forecasts = {match["id"]: match for match in raw["matches"]}
    rows = []
    for match in matches:
        if match["status"] != "FINISHED" or "score" not in match:
            continue
        original = forecasts.get(match["id"], {})
        published = match.get("published", False)
        forecast = scoring_forecast(match, original)
        if forecast["p"] is None:
            continue
        home, away = match["score"]
        day = datetime.fromisoformat(match["kickoff"]).date()
        rows.append({**forecast, "frequency": (frequency or {}).get("p"), "xg": match.get("xg"),
                     "score": match["score"], "result": 0 if home > away else 1 if home == away else 2,
                     "published": published, "week": (day - timedelta(days=day.weekday())).isoformat()})
    return rows
