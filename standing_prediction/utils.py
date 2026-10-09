from __future__ import annotations

import re
import unicodedata
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


def cache_max_age(season):
    today = datetime.now(timezone.utc)
    current_season = today.year if today.month >= 7 else today.year - 1
    return None if season is not None and int(season) < current_season else 3600


def cached_get(url, *, params=None, session=None, timeout=30, cache_dir=None, max_age=3600):
    cache_path = None
    if cache_dir is not None:
        public_params = {k: v for k, v in (params or {}).items() if k.lower() not in {"apikey", "api_key", "token"}}
        key = hashlib.sha256(json.dumps([url, public_params], sort_keys=True).encode()).hexdigest()
        cache_path = Path(cache_dir) / f"{key}.json"
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if max_age is None or time.time() - cached["fetched_at"] < max_age:
                return cached["content"]
        except (OSError, ValueError, KeyError, TypeError):
            pass

    getter = session.get if session is not None else requests.get
    for attempt in range(3):
        try:
            response = getter(url, params=params, timeout=timeout)
        except requests.RequestException:
            if attempt == 2:
                raise RuntimeError("Data request failed after 3 attempts.") from None
            time.sleep(attempt + 1)
            continue
        if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
            try:
                delay = min(5, max(1, float(response.headers.get("Retry-After", attempt + 1))))
            except ValueError:
                delay = attempt + 1
            time.sleep(delay)
            continue
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"Data request failed (HTTP {response.status_code}).") from None
        content = response.content.decode("utf-8-sig", errors="replace")
        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps({"fetched_at": time.time(), "content": content}), encoding="utf-8")
        return content


def normalize_team(name):
    name = str(name).lower().strip()
    name = name.replace("&", "and")
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"[^a-z0-9\s]", " ", name)
    tokens = [t for t in name.split() if t]

    stop = {
        "afc",
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

    normalized = " ".join(tokens).strip()
    aliases = {
        "man city": "manchester city", "man united": "manchester united",
        "man utd": "manchester united", "manchester utd": "manchester united",
        "wolves": "wolverhampton wanderers", "wolverhampton": "wolverhampton wanderers",
        "nott m forest": "nottingham forest", "nottm forest": "nottingham forest",
        "newcastle": "newcastle united", "tottenham": "tottenham hotspur",
        "west ham": "west ham united", "brighton": "brighton and hove albion",
        "leeds": "leeds united", "leicester": "leicester city",
        "sheffield utd": "sheffield united", "paris sg": "paris saint germain",
        "psg": "paris saint germain", "inter": "internazionale milano",
        "internazionale": "internazionale milano", "bayern munich": "bayern munchen",
    }
    return aliases.get(normalized, normalized)
