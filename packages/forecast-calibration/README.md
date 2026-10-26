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

Code for experiments that were not adopted (npxG with a penalty rate, expected XI and the EA prior) was removed from `main` on 24 October 2026; their reports in `docs/` link to commit `bb6a1b7`.

## Eleven-season miss report

Task 1's [report](../../docs/eleven-season-miss-report.md) and [complete tables](../../docs/eleven-season-miss-report-tables.md) describe the fixed no-odds blend without recalibration. With the saved feature dataset and provider caches:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python -m forecast_calibration.miss_report \
  --dataset /Users/hedibelkahia/codes/football/out/global-calibration/features/dataset.csv \
  --cache-dir /Users/hedibelkahia/codes/football/.cache --out-dir out/miss-report
```

This is offline: missing caches fail. The frequency baseline requires result caches for 2010/11 onward; model replay needs the original 2014/15+ results and Understat league listings, and the pre-goal diagnostic uses raw `understat/matches/` responses. It checks the exact dataset hash, replays goal expectations at the saved origins, verifies saved probabilities and writes coverage, per-match diagnostics, full contract tables, clustered SEs and input/output hashes under `out/`. `--workers` defaults to four and `--replay-only` prepares resumable replays. No calibration artifact or site data is written.

## Betting backtest feasibility

The [Task 1 report](../../docs/backtest-feasibility.md) joins the saved no-odds forecasts to cached raw prices, without refitting. It compares six fixed selection rules, flat and quarter-Kelly stakes, three price sources and pre-closing/closing prices:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python -m forecast_calibration.backtest_feasibility --out-dir out/backtest-feasibility
```

This command is offline and hash-checks the dataset. Outputs default to `out/`. It writes coverage, bets, all 72 summaries, season/league/price-band breakdowns, seeded match-date bootstrap intervals and preset parity numbers for Task 3. The eleven seasons are calibration in-sample; their walk-forward strengths do not make them an independent betting holdout. `select_bets`, `stake_bets`, `summarize` and `bootstrap_indices` provide the Python reference for the later browser engine.

## Backtest season exports

Task 3 replays the saved historical features to recover expected goals, and reconstructs the current season at the same Tuesday/Friday origins. Global calibration stays fixed. Build the twelve season files locally:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python scripts/build_backtest_data.py --offline --workers 4
```

`out/backtest/<season>.json` contains compact columns, all covered raw 1X2 bookmakers, source/identity hashes, separate replayed/published cohorts, missing-data coverage and twelve Python parity summaries. `out/backtest-build/parts` caches each league-season replay against its actual inputs. Historical files freeze while calibration is unchanged; `--rebuild` explicitly regenerates them. A second identical current-season build retains the file and its timestamp. Missing source caches fail offline; omit `--offline` to refresh expired current inputs. A failed refresh leaves the previous backtest file in place.

Use `--current-only` for the optional daily step. Published receipts are copied without changing them, with closing execution only. Receipts lacking a historical-price join remain visible with null prices; the engine counts them as missing-price voids. Official historical rounds, Stakes and European ratings remain null without dated evidence. Provider IDs are retrospective display/link metadata, never forecast inputs. The [contract](../../docs/backtest-data-contract.md) and [ADR 0003](../../docs/adr/0003-browser-betting-backtests.md) define the boundary.

Historical-price publication is authorized. Local output remains the default; pass `--dest site/data/backtest` to build published files and their availability manifest. `ENABLE_BACKTEST=1` is the single deployment switch for the tab and scheduled current-season export; it defaults off. For local previews, set `BACKTEST_ENABLED` to `true` in the preview's `assets/features.js`. See [ADR 0004](../../docs/adr/0004-backtest-deployment-switch.md).
