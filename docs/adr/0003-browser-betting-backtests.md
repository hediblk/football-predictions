---
status: accepted
date: 2026-10-25
---

# Run betting backtests in the browser over checked Python exports

The [Backtest plan](../backtest-plan-2026-10-24.md) adds a strategy tool over the existing standalone forecasts. Python still owns forecasting and historical replay, as required by [ADR 0001](0001-site-model-boundary.md). Browser code filters exported matches and settles hypothetical 90-minute bets; it does not fit strengths, simulate football results or change forecast probabilities.

## Decision

- Export one compact columnar JSON file per season through `scripts/build_backtest_data.py`. Include dated forecasts, results, raw decimal prices, explicit missing-data coverage, source hashes and Python-computed parity summaries. The [backtest contract](../backtest-data-contract.md) defines values and timing.
- Keep historical per-match prices under `out/backtest/` while D1, permission to publish football-data.co.uk prices, is unresolved. Public export requires the deliberate `--publish` option. Scheduled publication additionally requires `PUBLISH_BACKTEST_PRICES=1`; its default is off. This ADR does not resolve D1 or authorize contacting the source owner.
- Rebuild the current-season file as an optional refresh step, atomically replacing it only after validation. On failure retain its prior bytes and timestamp and continue the football refresh. Past files remain frozen while calibration is unchanged; an explicit rebuild can revise a local file without rewriting archived odds or forecast receipts.
- Read the saved calibration artifact without recalibration. Reconstruct historical team fits at the existing Tuesday/Friday origins, and keep published receipts as a separate forecast kind with closing-price execution only. Historical calibration seasons stay labelled in-sample; current-season data is unseen by calibration but can become strategy-selection data.
- Implement the strategy evaluator as a pure JavaScript module. Match its preset summaries with Python, including the same portable random sequence and bootstrap interpolation. Extend the existing headless browser check ([ADR 0002](0002-site-browser-checks.md)); commit only artificial parity prices, with optional explicit checks of local season files.

## Consequences

The tool needs no server or frontend framework. Every public price file must pass the existing schema and consistency boundary. A price average or maximum is an aggregate benchmark, not proof of execution at a bookmaker; missing quotes never become fair or synthetic prices. Unavailable historical rounds, Stakes tags or ratings stay unknown and cannot satisfy corresponding filters.

Tasks 3 and 4 add exports and the evaluator. The Backtest tab, additional markets and paper trading remain separate tasks. This decision extends the checked data boundary without changing its forecasting responsibilities.
