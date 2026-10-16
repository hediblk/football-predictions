from collections import Counter, defaultdict
import html
import math

from standing_prediction.squads import name_score


def aliases(player):
    ea = player.get("ea") or {}
    verified = (player.get("identity_override") or {}).get("aliases", [])
    return [player["name"], ea.get("name", ""), ea.get("common_name", ""), *verified]


def identify_appearance(name, players):
    name = html.unescape(name)  # Understat names arrive HTML-escaped (N&#039;Guessan)
    candidates = [(name_score(name, aliases(player), appearance=True), player["id"]) for player in players]
    candidates = [(score, pid) for score, pid in candidates if score is not None]
    if not candidates:
        return None
    best = min(score for score, _ in candidates)
    found = {pid for score, pid in candidates if score == best}
    return next(iter(found)) if len(found) == 1 else None


def compare_usage(club, detail, side):
    rows = detail.get("players", {}).get(side)
    if rows is None or "understat" not in detail.get("sources", {}):
        return {"status": "missing_match_sheet", "players": []}
    if (sum(row["position"] != "Sub" for row in rows) != 11 or
            len({row["id"] for row in rows}) != len(rows) or any(
                not isinstance(row["minutes"], (int, float)) or not math.isfinite(row["minutes"])
                or not 0 <= row["minutes"] <= 130 for row in rows)):
        return {"status": "invalid_match_sheet", "players": []}
    mapped = defaultdict(list)
    unresolved = []
    for row in rows:
        pid = identify_appearance(row["player"], club["players"])
        if pid is None:
            unresolved.append(row["player"])
        else:
            mapped[pid].append(row)
    for pid, observations in list(mapped.items()):
        if len(observations) > 1:
            unresolved.extend(row["player"] for row in observations)
            del mapped[pid]
    players = {row["id"]: row for row in club["players"]}
    usage = []
    for slot in club["best_xi"]["slots"]:
        pid = slot["player_id"]
        if pid is None:
            continue
        player = players[pid]
        observation = mapped.get(pid, [None])[0]
        state = "unknown" if unresolved else "did_not_play"
        minutes = None if unresolved else 0
        if observation:
            state = "substitute" if observation["position"] == "Sub" else "started"
            minutes = observation["minutes"]
        usage.append({"id": pid, "ea_id": player["ea"]["id"], "name": player["name"], "role": slot["role"],
                      "status": state, "minutes": minutes,
                      "understat_id": observation["id"] if observation else None})
    counts = Counter(row["status"] for row in usage)
    complete = len(usage) == 11 and not counts["unknown"]
    return {"status": "complete" if complete else "partial", "players": usage, "counts": dict(counts),
            "unresolved_appearances": unresolved, "matched_appearances": sum(len(items) for items in mapped.values()),
            "total_appearances": len(rows),
            "ideal_minutes_share": round(100 * sum(min(row["minutes"], 90) for row in usage) / 990, 1) if complete else None,
            "sources": detail["sources"]}
