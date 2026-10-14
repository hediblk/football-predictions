import math
from datetime import datetime, timedelta

import pandas as pd


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
        "calibration": bins, "weekly": series, "market": None,
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
        if published:
            p, elo, call = match.get("p"), match.get("elo"), match.get("call", [])[:2]
        elif "p_home" in original:
            p = [original[key] for key in ("p_home", "p_draw", "p_away")]
            elo, call = original.get("elo"), original.get("pick_score", [])[:2]
        else:
            continue
        if p is None:
            continue
        home, away = match["score"]
        day = datetime.fromisoformat(match["kickoff"]).date()
        rows.append({"p": p, "elo": elo, "frequency": (frequency or {}).get("p"),
                     "score": match["score"], "call": call, "result": 0 if home > away else 1 if home == away else 2,
                     "published": published, "week": (day - timedelta(days=day.weekday())).isoformat()})
    return rows
