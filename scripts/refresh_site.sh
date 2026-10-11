#!/usr/bin/env bash
# Rerun every forecast shown on the website, then rebuild site/data.
# Requires FOOTBALL_DATA_API_KEY in .env (or the environment) and both packages installed:
#   pip install -e . -e packages/champions-league
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=out/site
N_SIM=${N_SIM:-10000}
mkdir -p "$OUT"

failed=()
for competition in PL PD BL1 SA FL1; do
  echo "== $competition"
  football-predict --competition "$competition" --n-sim "$N_SIM" --no-use-odds --out-dir "$OUT" || failed+=("$competition")
  sleep 15  # football-data.org free tier allows 10 requests per minute
done
echo "== UCL"
sleep 45
football-ucl --n-sim "$N_SIM" --out-dir "$OUT" || failed+=(UCL)

# A failed competition keeps its previous outputs in $OUT, so the site shows its last good forecast.
python scripts/build_site_data.py --src "$OUT" --dest site/data
if ((${#failed[@]})); then
  echo "Kept previous forecasts for: ${failed[*]}" >&2
  exit 1
fi
