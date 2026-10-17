# Football forecast calibration

An installable calibration package, separate from `standing_prediction`. It reuses that package's Dixon–Coles, Elo and xG models to fit one versioned set of global weights. Forecasts read the saved artifact; they never rerun this calibration automatically.

From the repository root:

```bash
pip install -e . -e packages/forecast-calibration
football-calibrate --weights-out src/standing_prediction/calibrated_weights.json
```

The default run covers E0, SP1, D1, I1 and F1 in 2015/16–2025/26, with 2014/15 warm-up. Every match appears once, forecast from the preceding Tuesday or Friday at 00:00 UTC. The models see only results available before that origin. Fits reuse up to two prior seasons and are shared by matches at the same origin. Per-season feature files are resumable.

Pre-closing market averages (`Avg`, then `BbAv`) are preferred, with Bet365 as a fallback. Complete quotes are de-margined; closing odds are excluded. Collection dates are approximate, based on the [provider's notes](https://www.football-data.co.uk/notes.txt). Results and xG are assumed available the next UTC day after the local match date. Historical publication timestamps cannot be reconstructed.

Each league-season contributes equally. The objective gives equal weight to forecasts with odds masked and forecasts with odds present. This fits the main/Elo ratio for the many future fixtures without odds as well as the market share for quoted fixtures. Market weight is capped at `1 - 1e-6` to keep that ratio defined even if the fitted optimum is entirely market-based. The artifact also records the renormalized no-odds weights. The xG grid is 0, 0.25, 0.5, 0.75, 1, and each positive weight is tried with xG scales 1, 1.1, 1.2, 1.3, 1.4 and 1.5; H2H stays off. Decay stays at 0.003. The ridge defaults to 2, chosen in a separate decay and ridge search ([Plan C](../../PLAN.md)).

The latest two seasons are held out chronologically before the final refit. Leave-one-season-out and leave-one-league-out folds report stability, independently selecting xG and blend weights on each training fold. P1, N1, B1, T1, G1 and SC0 are evaluated only as external robustness leagues, without xG. The artifact records losses, baseline comparisons, fold spread, coverage, data/code hashes and a version.

To refit saved features without downloading or refitting team models:

```bash
football-calibrate --dataset out/global-calibration/features/dataset.csv \
  --robustness-dataset out/global-calibration/robustness/dataset.csv \
  --weights-out src/standing_prediction/calibrated_weights.json
```

Use `--help` for a smaller run or custom output location. A calibration artifact summarizes match-level performance; it cannot make the model permanently optimal or establish that standings probabilities are calibrated.

`python -m forecast_calibration.npxg all` runs the same protocol for non-penalty xG and a team penalty rate ([report](../../docs/npxg-penalty-rate.md)). It writes to `out/npxg-penalty-rate` and does not touch the artifact.

## Offline expected-XI evaluation

Task 8 reuses this package's historical origins and loaders, without writing calibration settings or forecasts:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python -m forecast_calibration.expected_xi \
  --cache-dir /Users/hedibelkahia/codes/football/.cache --out-dir out/expected-xi
```

This requires the saved provider caches and committed Understat player archive; it makes no HTTP requests. It compares latest XI, decayed start share, missed-game decay and an actual-starters oracle, selects weights before 2024/25, and checks the last two seasons unchanged. All CSVs and input/code hashes stay under `out/`. See the [protocol, results and limits](../../docs/expected-xi-forecast-adjustment.md). The default prior is flat; `--prior module:function` still accepts plain `(players, before_season)` callables.

Task 7b's EA prior also fits slopes on earlier seasons. Use its explicit adapter, with compact rating vintages in the player cache:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python -m forecast_calibration.expected_xi \
  --cache-dir /Users/hedibelkahia/codes/football/.cache --prior ea \
  --out-dir out/expected-xi-ea
```

`--ea-cache` overrides the default `CACHE_DIR/players`. Each season's selected ridge is refitted after its candidate search so its saved effects use the selected slopes. EA columns cover the fixed matched identity catalogue plus past appearances; future evaluation sheets do not set the prior's position-group means. The manifest hashes the identity table, vintage metadata and compact rating files.

## Eleven-season miss report

Task 1's [report](../../docs/eleven-season-miss-report.md) and [complete tables](../../docs/eleven-season-miss-report-tables.md) describe the fixed no-odds blend without recalibration. With the saved feature dataset and provider caches:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python -m forecast_calibration.miss_report \
  --dataset /Users/hedibelkahia/codes/football/out/global-calibration/features/dataset.csv \
  --cache-dir /Users/hedibelkahia/codes/football/.cache --out-dir out/miss-report
```

This is offline: missing caches fail. The frequency baseline requires result caches for 2010/11 onward; model replay needs the original 2014/15+ results and Understat league listings, and the pre-goal diagnostic uses raw `understat/matches/` responses. It checks the exact dataset hash, replays goal expectations at the saved origins, verifies saved probabilities and writes coverage, per-match diagnostics, full contract tables, clustered SEs and input/output hashes under `out/`. `--workers` defaults to four and `--replay-only` prepares resumable replays. No calibration artifact or site data is written.
