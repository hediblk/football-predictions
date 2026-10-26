---
status: accepted
date: 2026-10-26
supersedes: "ADR 0003: unresolved D1 and separate price-publication safeguards"
---

# Control Backtest with one deployment flag

The user confirmed on 26 October 2026 that historical prices may be published and requested removal of the publication safeguards. D1 is resolved. The checked Python-export/browser-engine boundary in [ADR 0003](0003-browser-betting-backtests.md) still applies.

## Decision

- Use the GitHub Actions repository variable `ENABLE_BACKTEST=1` to enable the feature; unset or any other value disables it.
- During deployment, write `site/assets/features.js` before asset stamping and browser checks. The committed module defaults to disabled. A flag change takes effect after redeployment and page reload.
- Hide the tab until enabled. Disabled direct and saved Backtest links return to Tables without importing Backtest code, fetching its data or starting its worker.
- Run the optional current-season exporter only when enabled, writing into the staged site with `--dest`. Retain prior data and timestamps on failure. The exporter maintains the season availability manifest after successful builds.
- Remove `PUBLISH_BACKTEST_PRICES`, the Backtest exporter's `--publish` option and the historical-price output-directory restrictions. Local export still defaults to `out/backtest/`; `--dest` selects a site or preview directory.
- Exercise enabled and disabled routing in the existing browser check. Feature configuration participates in the existing asset hash.

## Consequences

One deployment switch controls the UI and scheduled Backtest refresh without a new service or dependency. Disabling the feature retains existing season files; the flag controls availability, not access to files already published. Initial historical exports remain an explicit build, while daily refresh updates only the current season.
