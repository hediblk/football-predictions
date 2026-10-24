#!/usr/bin/env bash
# Rerun every forecast shown on the website, then rebuild site/data.
# Requires FOOTBALL_DATA_API_KEY in .env (or the environment) and both packages installed:
#   pip install -e . -e packages/champions-league
# A failed competition keeps its last published data; all-fail or invalid exports fail the refresh.
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=out/site
N_SIM=${N_SIM:-10000}
mkdir -p "$OUT"

warn() {
  if [[ -n "${GITHUB_ACTIONS:-}" ]]; then echo "::warning::$1"; else echo "WARNING: $1" >&2; fi
}

clear_outputs() {
  rm -f "$OUT/$1"_{summary,position_probs,standings_snapshot,matches_snapshot,club_ratings}.csv \
    "$OUT/$1"_{forecast,metadata,match_forecasts,stakes,espn_xg}.json
}

failed=()
for competition in PL PD BL1 SA FL1; do
  echo "== $competition"
  # Remove stale outputs so a failed run can't republish an old forecast as new.
  prefix=$(echo "$competition" | tr '[:upper:]' '[:lower:]')
  clear_outputs "$prefix" || exit 1
  if ! football-predict --competition "$competition" --n-sim "$N_SIM" --no-use-odds --out-dir "$OUT"; then
    clear_outputs "$prefix" || exit 1
    failed+=("$competition")
  fi
  sleep 15  # football-data.org free tier allows 10 requests per minute
done
echo "== UCL"
sleep 45
clear_outputs cl || exit 1
if ! football-ucl --n-sim "$N_SIM" --out-dir "$OUT"; then
  clear_outputs cl || exit 1
  failed+=(UCL)
fi

if ((${#failed[@]})); then
  warn "Forecast failed for ${failed[*]}; the site keeps their previous data."
fi
if ((${#failed[@]} == 6)); then exit 1; fi

# Validate fresh and retained data together before replacing the published files.
candidate=$(mktemp -d) || exit 1
trap 'rm -rf "$candidate"' EXIT
cp -R site/data "$candidate/data" || exit 1
python scripts/fetch_ucl_xg.py --src "$OUT" || warn "ESPN Champions League xG failed; forecasts are still published."
python scripts/build_site_data.py --src "$OUT" --dest "$candidate/data" || exit 1
python scripts/fetch_match_events.py --src "$OUT" --data "$candidate/data" || warn "Match event ingestion failed; forecasts are still published."
python scripts/build_club_profiles.py --data "$candidate/data" || warn "Club profiles failed; keeping the previous profiles."
# Squad publication is optional: build in isolation so any failure retains every old file and timestamp.
squad_candidate=$(mktemp -d) || exit 1
cp -R "$candidate/data" "$squad_candidate/data" || exit 1
if python scripts/build_squads.py --download-players --publish \
    --players .cache/players/ea/fc27-2026-09-12.csv --roster-cache .cache/players/rosters \
    --site-data "$squad_candidate/data" && \
    python scripts/build_squad_usage.py --site-data "$squad_candidate/data" \
    --players .cache/players/ea/fc27-2026-09-12.csv && \
    python scripts/validate_site_data.py --data "$squad_candidate/data" --site site; then
  cp -R "$squad_candidate/data/squads" "$candidate/data/" || exit 1
else
  warn "Squad refresh failed; keeping previous squad files and timestamps."
fi
rm -rf "$squad_candidate"
python scripts/validate_site_data.py --data "$candidate/data" --site site || exit 1
cp -R "$candidate/data/." site/data || exit 1
