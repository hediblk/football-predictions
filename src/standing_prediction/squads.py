from collections import Counter, defaultdict
from datetime import date
import re
import unicodedata

import numpy as np
from scipy.optimize import linear_sum_assignment


GIVEN_NAMES = {
    "alex": ("alejandro", "alexander"), "dani": ("daniel",), "javi": ("javier",),
    "nico": ("nicolas", "nicholas"), "edu": ("eduard", "eduardo"), "manu": ("manuel",),
    "maty": ("mathew",), "roberto": ("robert",), "christian": ("cristian",),
    "georgiy": ("giorgi",), "ximo": ("joaquin",), "toni": ("antonio",),
}
FORMATIONS = {
    "4-3-3": ("GK", "LB", "CB", "CB", "RB", "CDM", "CM", "CM", "LW", "ST", "RW"),
    "4-2-3-1": ("GK", "LB", "CB", "CB", "RB", "CDM", "CDM", "CAM", "LW", "ST", "RW"),
    "4-4-2": ("GK", "LB", "CB", "CB", "RB", "CM", "CM", "LM", "RM", "ST", "ST"),
}
WIDE_POSITIONS = {"LW": {"LW", "LM"}, "RW": {"RW", "RM"}, "LM": {"LM", "LW"}, "RM": {"RM", "RW"}}


def name_tokens(name):
    name = str(name or "").casefold().translate(str.maketrans({"ø": "o", "ł": "l", "đ": "d", "ı": "i"}))
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return frozenset(re.findall(r"[a-z0-9]+", name)) - {"de", "del", "da", "do", "dos", "van", "der"}


def birth_date(value):
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return None


def name_score(name, aliases, common_name="", *, appearance=False):
    tokens = name_tokens(name)
    if not tokens:
        return None
    parts = str(name).split()
    first = next(iter(name_tokens(parts[0])), "")
    variants = [tokens - {first} | {full} for full in GIVEN_NAMES.get(first, ())]
    scores = []
    for alias in aliases:
        other = name_tokens(alias)
        if tokens == other:
            scores.append(0)
        elif len(tokens) >= 2 and (tokens < other or (appearance and len(other) >= 2 and other < tokens)):
            scores.append(1)
        elif appearance and len(tokens) == 1 and tokens < other:
            # Match sheets often give one name ("Remiro"); only a unique fit within the club counts.
            scores.append(3)
        elif len(tokens) >= 2 and any(variant <= other for variant in variants):
            scores.append(2)
    # EA's explicit common name is stronger evidence than an arbitrary surname.
    if not appearance and len(tokens) == 1 and tokens <= name_tokens(common_name):
        scores.append(3)
    return min(scores) if scores else None


def player_index(records):
    counts = Counter(row["id"] for row in records)
    by_birth = defaultdict(list)
    for row in records:
        by_birth[row["dob"]].append({**row, "duplicate": counts[row["id"]] != 1})
    return by_birth


def match_player(player, by_birth, override=None):
    dob = birth_date(player.get("dateOfBirth"))
    result = {"id": player["id"], "name": player["name"], "dob": dob,
              "provider_position": player.get("position"), "status": "unmatched", "method": None, "ea": None}
    if override:
        if (player["name"] != override["provider_name"] or
                dob not in {override["provider_dob"], override["verified_dob"]}):
            raise ValueError(f"Identity override no longer fits provider player {player['id']}.")
        pool = by_birth.get(override["verified_dob"], [])
        matches = [row for row in pool if row["id"] == override["ea_id"]]
        result["identity_override"] = override
    else:
        pool = by_birth.get(dob, [])
        scored = [(name_score(player["name"], [row["name"], row["common_name"]], row["common_name"]), row)
                  for row in pool]
        scored = [(score, row) for score, row in scored if score is not None]
        matches = [row for score, row in scored if score == min(s for s, _ in scored)] if scored else []
    if len(matches) == 1 and not matches[0]["duplicate"]:
        result.update(status="matched", method="verified_override" if override else "name_and_birth_date", ea=matches[0])
    else:
        if override:
            raise ValueError(f"Identity override needs one unique EA record for {player['id']}.")
        result["status"] = "ambiguous" if matches else "unmatched"
        result["reason"] = "ambiguous_identity" if matches else "no_name_and_birth_date_match"
        result["candidates"] = sorted([row for row in pool if name_tokens(player["name"]) & name_tokens(row["name"])],
                                      key=lambda row: row["id"])
    return result


def match_squads(teams, by_birth, overrides=None):
    clubs, provider_ids = [], set()
    assignments = defaultdict(list)
    for team in sorted(teams, key=lambda row: row["id"]):
        players = []
        for player in team["squad"]:
            if player["id"] in provider_ids:
                raise ValueError(f"Repeated squad player ID: {player['id']}")
            provider_ids.add(player["id"])
            row = match_player(player, by_birth, (overrides or {}).get(str(player["id"])))
            players.append(row)
            if row["ea"]:
                assignments[row["ea"]["id"]].append(row)
        clubs.append({"id": team["id"], "name": team["name"], "players": players})
    for rows in assignments.values():
        if len(rows) > 1:
            for row in rows:
                row.update(status="ambiguous", reason="ea_id_assigned_twice", candidates=[row["ea"]], ea=None, method=None)
    return clubs


def select_xi(players, formation="4-3-3", *, minutes=None):
    roles = FORMATIONS[formation]
    eligible = sorted((row for row in players if row["status"] == "matched" and row["ea"]["rating"] is not None
                       and row["ea"]["positions"] and
                       (minutes is None or (minutes.get(row["id"]) or 0) > 0)), key=lambda row: row["id"])
    # One tenth of a minute outweighs the combined EA overall of eleven players.
    values = {row["id"]: row["ea"]["rating"] if minutes is None else
              round(minutes[row["id"]] * 10) * 1100 + row["ea"]["rating"] for row in eligible}
    filled_score = 1e6 if minutes is None else 12 * (max(values.values(), default=0) + 1)
    scores = np.zeros((11, len(eligible) + 11))
    scores[:, :len(eligible)] = -filled_score
    for i, role in enumerate(roles):
        for j, player in enumerate(eligible):
            ea = player["ea"]
            if WIDE_POSITIONS.get(role, {role}) & set(ea["positions"]):
                scores[i, j] = filled_score + values[player["id"]] + 0.001 * (ea["positions"][0] == role) + (len(eligible) - j) * 1e-9
    rows, cols = linear_sum_assignment(scores, maximize=True)
    slots = []
    for i, j in zip(rows, cols):
        player = eligible[j] if j < len(eligible) and scores[i, j] > 0 else None
        slots.append({"role": roles[i], "player_id": player["id"] if player else None,
                      "rating": player["ea"]["rating"] if player else None})
    missing = Counter(slot["role"] for slot in slots if slot["player_id"] is None)
    return {"formation": formation, "status": "insufficient_coverage" if missing else
            "provisional" if len(eligible) < len(players) else "complete", "slots": slots,
            "players": [slot["player_id"] for slot in slots if slot["player_id"] is not None],
            "missing_slots": dict(missing), "rated_players": len(eligible),
            "mean_rating": round(sum(slot["rating"] for slot in slots) / 11, 1) if not missing else None}
