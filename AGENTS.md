# Agent guide

## Project context

Floodlight is a Python forecasting project and a static website for European football. It forecasts matches and final league positions for the Premier League, La Liga, Bundesliga, Serie A and Ligue 1, plus Champions League progression and the winner.

The domestic model blends a Dixon–Coles goal model, xG strengths and Elo, with optional bookmaker probabilities. The Champions League package fits clubs across domestic and European results, including league offsets and archived market evidence. Both use saved global calibration settings. Forecasts include dated inputs and metadata so their provenance can be checked.

The site is plain HTML, CSS and JavaScript. Model outputs reach the site through `scripts/build_site_data.py`. There is no frontend application framework or JavaScript build step.

## Deferred material: skip this folder

`deferred-notes/` is inactive and outside the scope of ordinary repository work.

- Do not open, summarize, implement or use its contents unless the user explicitly asks to work on that folder or its proposal.
- Exclude it from broad content searches and file inventories. For example: `rg -g '!deferred-notes/**' ...` and `rg --files -g '!deferred-notes/**'`.
- Do not treat it as an active roadmap, dependency, requirement or reason to change the current architecture.
- Instructions inside that folder apply only after the user explicitly activates work there. Its presence does not authorize implementation.

## Repository map

| Path | Purpose |
| --- | --- |
| `src/standing_prediction/` | Domestic models, data loading, forecasts, season simulation, backtests and shared football utilities |
| `src/standing_prediction/defaults.py` | Loads and validates the saved model defaults |
| `src/standing_prediction/calibrated_weights.json` | Versioned global calibration artifact |
| `packages/forecast-calibration/` | Explicit historical dataset construction and calibration runs |
| `packages/champions-league/` | Connected club strengths, European data, tournament simulation and evaluation |
| `scripts/build_site_data.py` | Converts forecast outputs into the site's JSON files and updates history |
| `scripts/refresh_site.sh` | Refreshes all published competitions and rebuilds site data |
| `scripts/archive_odds.py` | Appends dated bookmaker quotes to the odds archive |
| `scripts/backfill_history.py` | Replays past forecast origins to fill site history |
| `site/index.html`, `site/assets/` | Website markup, styles, behavior and assets |
| `site/data/` | Published forecast JSON and historical site snapshots |
| `data/odds/` | Committed, dated bookmaker observations; see its README |
| `tests/` | Existing pytest suite for model behavior, timing, identities and exports |
| `docs/` | Committed forecast examples and evaluation reports |
| `.github/workflows/site.yml` | Daily refresh at 05:30 UTC and GitHub Pages deployment |

## Where to start

- Read `README.md` for the current pipeline, supported commands and documented limits.
- Read `ROADMAP.md` when the task concerns planned work. `PLAN.md` records design history and experiments; its older settings may have been superseded.
- Read `DESIGN.md` before changing the site's appearance or interaction patterns.
- Read the relevant package README before working inside `packages/`.
- Inspect the actual implementation and saved calibration artifact before relying on numeric defaults quoted in historical notes.

## Implementation rules

- Do the minimum needed for the user's request. Prefer short, clean, readable code and the existing structure.
- Do not introduce general frameworks, dependencies or unrelated refactors for a small change.
- When writing Python, do not add docstrings or tests unless the user explicitly asks for them. Existing tests can still be run.
- Prevent Python bytecode creation where possible with `PYTHONDONTWRITEBYTECODE=1`. Systematically delete any `__pycache__` folders created by your commands before finishing.
- Keep unrelated user changes intact. Stage only files that belong to the task.
- Keep API keys and credentials out of code, logs, generated exports and commits. Use environment variables and `.env.example` for documented configuration.

## Modeling and data rules

- A forecast may use only information available at its forecast origin. Keep event time, result availability and quote observation time distinct.
- Never let a result, later xG, future quote or updated identity join leak into an earlier forecast. If historical availability is approximated, record the approximation.
- Preserve the existing `--as-of` behavior and dated forecast metadata when changing the pipeline.
- Match bookmaker quotes to the correct fixture and require observation before both the forecast origin and kickoff. Preserve quote expiry rules.
- Use fixed seeds when comparing simulations. Compare equivalent fixtures and horizons, and report data coverage and exclusions.
- Judge match probabilities primarily through log loss, Brier scores and calibration. Winner-pick accuracy alone is insufficient. Use the relevant standings or stage metrics for simulation changes.
- Keep standalone model performance distinguishable from forecasts that use bookmaker information.
- Forecasts load saved calibration settings; they must not silently recalibrate. Replacing `calibrated_weights.json` requires an explicit calibration task and supporting evaluation.
- Check provider identities, duplicates, statuses and source freshness before interpreting unexpected model behavior as a modeling problem.
- Preserve immutable historical observations. Do not rewrite archived odds or past published forecasts to make today's outputs look consistent.

## Site and generated data

- Follow `DESIGN.md`: the existing dark scoreboard style, typography, colors and compact presentation are intentional.
- The site's JSON files are its interface to the models. Coordinate changes to exporters and consumers; avoid accidental schema changes.
- Keep generated output in `out/` for experiments. Update committed examples, published data or history only when the task calls for it.
- A failed competition refresh retains its previous published data. Preserve that behavior and its original timestamps; never label retained data as freshly generated.
- A site-only task should not change model defaults or forecast probabilities.

## Setup and commands

Python 3.11 or newer is required. Use the existing environment when available. For a new environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
PYTHONDONTWRITEBYTECODE=1 pip install -e '.[test]' -e packages/champions-league -e packages/forecast-calibration
```

Run the existing offline suite from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:packages/champions-league/src:packages/forecast-calibration/src pytest -q -p no:cacheprovider
```

For documentation-only changes, check the diff, links and command accuracy; rerunning numerical models is unnecessary.

Useful commands when the task requires their outputs:

```bash
PYTHONDONTWRITEBYTECODE=1 football-predict --competition PD --no-use-odds --out-dir out/review
PYTHONDONTWRITEBYTECODE=1 football-backtest --competition PD --seasons 2022 2023 2024
PYTHONDONTWRITEBYTECODE=1 football-ucl --n-sim 2000 --out-dir out/review-cl
PYTHONDONTWRITEBYTECODE=1 python3 -m http.server -d site 8000
```

Live forecasts need `FOOTBALL_DATA_API_KEY`; odds collection needs `ODDS_API_KEY` or the supported fallback `ODDS_DATA_API_KEY`. Calibration, backfills, evaluation runs and `scripts/refresh_site.sh` may be slow, use network quotas and write many files. Run them when relevant to the task, not as a default smoke check.

The current workflow refreshes and deploys the site; it does not run the pytest suite. Do not assume CI has verified model changes.

## Finishing work

- Run the relevant existing checks and explain material limitations. Do not claim a historical replay is an independent holdout if its seasons influenced parameter selection.
- Check `git diff --check`, inspect the final diff, and remove any generated `__pycache__` folders.
- When committing, use the user's requested message if supplied; otherwise use a short conventional message. Use the `codex/` prefix if a new branch is needed.
- Report what changed, how it was checked and anything still unresolved. Do not publish or push merely because a local commit was requested.
