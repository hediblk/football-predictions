from __future__ import annotations

import re
import unicodedata


def normalize_team(name):
    name = str(name).lower().strip()
    name = name.replace("&", "and")
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"[^a-z0-9\\s]", " ", name)
    tokens = [t for t in name.split() if t]

    stop = {
        "fc",
        "cf",
        "cd",
        "ud",
        "sd",
        "rc",
        "rcd",
        "ca",
        "ac",
        "sc",
        "club",
        "de",
        "del",
        "la",
        "el",
        "the",
        "balompie",
        "futbol",
        "football",
        "deportivo",
    }
    tokens = [t for t in tokens if t not in stop]

    #common abreviation fixes
    if tokens[:1] == ["ath"] and "madrid" in tokens:
        tokens[0] = "atletico"
    elif tokens[:1] == ["ath"] and "bilbao" in tokens:
        tokens[0] = "athletic"

    if len(tokens) >= 2 and tokens[0] == "real" and tokens[1] != "madrid":
        tokens = tokens[1:]

    drop_tail_for = {"celta": {"vigo"}, "espanyol": {"barcelona"}, "athletic": {"bilbao"}}
    if len(tokens) >= 2 and tokens[0] in drop_tail_for and tokens[1] in drop_tail_for[tokens[0]]:
        tokens = tokens[:1]

    aliases = {"espanyol": "espanol"}
    tokens = [aliases.get(t, t) for t in tokens]

    if "vallecano" in tokens and "rayo" in tokens:
        tokens = [t for t in tokens if t not in {"rayo"}]
    if tokens == ["vallecano", "madrid"]:
        tokens = ["vallecano"]

    return " ".join(tokens).strip()
