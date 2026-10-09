# Package plan

Keep `src/standing_prediction` as the main product, with one current notebook in `notebooks/laliga_prediction.ipynb` and a concise README. Notebook and CLI behavior should come from the package.

## Implemented

- Installable package with editable installation, pinned core dependencies, CLI commands, and environment-key setup.
- Shared `run_prediction` API returning probabilities, summary, standings, and metadata; one notebook uses the same API and chart styling.
- Time-decayed Dixon–Coles plus Elo, two prior seasons by default, season regression, and neutral strength for teams without observed history.
- Optional bookmaker blending with timestamp/date-aware matching; undated historical odds excluded from dated forecasts. Calibration remains optional.
- Full season-schedule checks, scoreline simulation, practical league-specific ranking, and La Liga head-to-head subset reapplication.
- Vectorized simulations, expected points/positions, point percentiles, event probabilities, and Monte Carlo standard errors.
- Chart-first HTML/notebook output with continuous nonlinear colors, two-decimal percentages, saved provenance, input snapshots, and timestamped forecast archives.
- Chronological historical snapshots and expanding-season calibration evaluation, with match, position, and event metrics. Official completed-season prediction exports bypass fitting.

## Next priorities

1. **Evaluate model settings on held-out seasons.** Compare prior-history length, decay, blend weights, and optional calibration using the same dated snapshots. Prefer position RPS and event Brier scores alongside match log loss; overlapping horizons are not independent observations.
2. **Build a usable dated odds archive.** Retain observation and kickoff timestamps, track fixture coverage, and compare the blend with bookmaker probabilities on the same covered matches. Do not infer historical availability from today's odds.
3. **Close official-table gaps where data supports it.** Add dated points adjustments and deciding playoff handling before claiming official-table equivalence. Keep score-based targets and conditional uncertainty explicit until then.

Add richer inputs only after these comparisons identify a clear need. Keep tournament formats and larger model experiments outside the current league-package scope.
