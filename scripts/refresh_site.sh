#!/usr/bin/env bash
# Rerun every forecast shown on the website, then rebuild site/data.
# Requires FOOTBALL_DATA_API_KEY in .env (or the environment) and both packages installed:
#   pip install -e . -e packages/champions-league
# Exits nonzero only when every forecast failed; a failed competition keeps its last published data.
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=out/site
N_SIM=${N_SIM:-10000}
mkdir -p "$OUT"

warn() {
  if [[ -n "${GITHUB_ACTIONS:-}" ]]; then echo "::warning::$1"; else echo "WARNING: $1" >&2; fi
}

failed=()
for competition in PL PD BL1 SA FL1; do
  echo "== $competition"
  # Remove stale outputs so a failed run can't republish an old forecast as new.
  prefix=$(echo "$competition" | tr '[:upper:]' '[:lower:]')
  rm -f "$OUT/$prefix"_{summary,position_probs,standings_snapshot}.csv "$OUT/${prefix}_metadata.json"
  football-predict --competition "$competition" --n-sim "$N_SIM" --no-use-odds --out-dir "$OUT" || failed+=("$competition")
  sleep 15  # football-data.org free tier allows 10 requests per minute
done
echo "== UCL"
sleep 45
rm -f "$OUT"/cl_{forecast,metadata}.json "$OUT"/cl_standings_snapshot.csv
football-ucl --n-sim "$N_SIM" --out-dir "$OUT" || failed+=(UCL)

python scripts/build_site_data.py --src "$OUT" --dest site/data
if ((${#failed[@]})); then
  warn "Forecast failed for ${failed[*]}; the site keeps their previous data."
fi
((${#failed[@]} < 6))
