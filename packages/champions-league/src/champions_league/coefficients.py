import json
import math
import re

import requests

from standing_prediction.utils import cached_get

from champions_league.identities import canonical_team


RANKINGS_PAGE = "https://ar.uefa.com/nationalassociations/uefarankings/club/"
COEFFICIENTS_API = "https://comp.uefa.com/v2/coefficients"
UEFA_NAMES = {
    "paris": "paris saint germain", "atleti": "atletico madrid",
    "b dortmund": "borussia dortmund", "s bratislava": "slovan bratislava",
    "sporting cp lisbon": "sporting cp",
}


def fetch_coefficients(season, teams, cache=True):
    teams = tuple(teams)
    metadata = {
        "season": int(season), "source": COEFFICIENTS_API,
        "ranking_page": f"{RANKINGS_PAGE}?year={season}",
        "reference_period": f"{season - 5}/{str(season - 4)[-2:]}–{season - 1}/{str(season)[-2:]}",
        "matched": 0, "missing": list(teams), "complete": False,
    }
    cache_dir = ".cache/ucl-coefficients" if cache else None
    coefficients = {}
    try:
        page = cached_get(RANKINGS_PAGE, params={"year": season}, cache_dir=cache_dir, max_age=86400, timeout=10)
        key = re.search(r"window\.apiKey\s*=\s*['\"]([^'\"]+)['\"]", page)
        if key is None:
            raise ValueError("Official ranking page exposes no coefficient API configuration.")
        session = requests.Session()
        session.headers.update({"x-api-key": key.group(1)})
        for number in range(1, 11):
            params = {"coefficientRange": "OVERALL", "coefficientType": "MEN_CLUB",
                      "seasonYear": season, "page": number, "pagesize": 500, "language": "EN"}
            response = json.loads(cached_get(COEFFICIENTS_API, params=params, session=session,
                                            cache_dir=cache_dir, max_age=None, timeout=10))
            payload = response.get("data", {})
            members = payload.get("members", [])
            metadata["last_updated"] = payload.get("lastUpdateDate")
            for item in members:
                member, ranking = item.get("member", {}), item.get("overallRanking", {})
                if str(ranking.get("targetSeasonYear", season)) != str(season):
                    continue
                values = [ranking.get("totalValue"), ranking.get("nationalAssociationPoints")]
                values = [float(value) for value in values if value is not None]
                if not values or any(not math.isfinite(value) or value < 0 for value in values):
                    continue
                for column in ("internationalName", "displayName", "name", "shortName"):
                    if not isinstance(member.get(column), str):
                        continue
                    name = canonical_team(member[column])
                    name = UEFA_NAMES.get(name, name)
                    if name in teams:
                        coefficients[name] = max(values)
            if len(members) < 500:
                break
        if not coefficients:
            raise ValueError("Official feed contains no matching season club coefficients.")
    except (ValueError, KeyError, TypeError, RuntimeError, OSError) as exc:
        metadata["error"] = str(exc)
    metadata.update(matched=len(coefficients), missing=sorted(set(teams) - set(coefficients)),
                    complete=len(coefficients) == len(teams))
    return coefficients, metadata
