# Numerical protection

Implemented by [the numerical regression suite](../tests/test_numerical_regression.py), using [frozen cases and reviewed baselines](../tests/fixtures/numerical/README.md). [ADR 0001](adr/0001-site-model-boundary.md) records the boundary decision; published JSON has a separate [data contract](site-data-contract.md).

Run with `PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m pytest -q tests/test_numerical_regression.py` from the repository root after installing the pinned development environment in the README.

## Purpose

Detect unintended changes to fitting, production defaults, probability blending, score sampling, league ranking, and tournament progression. A regression failure means that behavior changed and needs investigation. Passing does not establish predictive accuracy: model improvements still need the historical evaluation described in [PLAN.md](../PLAN.md).

Use the same computational functions in production and tests. Small refactors that make frozen inputs injectable or remove duplicated calculations are in scope. Keep provider loading at the boundary; do not maintain a separate forecasting implementation just for tests or add a new abstraction unless it simplifies the production code.

## Frozen cases and coverage

| Case | Frozen inputs | Production behavior exercised |
| --- | --- | --- |
| Domestic season | Dated past results, xG with some missing values, a partially played season and consistent standings, remaining fixtures, and timestamped odds for some fixtures | Goal/xG/Elo fitting, quoted and unquoted blending, conditional score distributions, season simulation, league ranking, summary and match forecasts |
| Champions League | Results from several domestic leagues and European meetings, league identities, xG, archived market quotes, coefficients, standings, and a valid league-phase schedule | Joint strengths, league offsets and market shifts, match distributions, league-phase ranking, permitted draws, two-legged ties, stage progression, and the neutral final |

Check the input files into the repository. Small synthetic fixtures are acceptable when understandable and documented, but do not randomly regenerate them during the regression run. The domestic case needs enough clubs to make title, top-four, and bottom-three events distinct. The UCL case needs the real tournament shape: 36 clubs and 144 league-phase matches, with eight distinct opponents and four home/four away games per club.

The existing domestic calculation path is `fit_prediction_models` → `build_fixture_specs` → `simulate_season_scores` → `forecast_summary`, with `fixture_forecasts` for match outputs. UCL uses `fit_strengths`, `MatchupCache`, and `simulate_tournament`. A regression must include fitting; substituting a hand-written strength model would only protect the simulator.

Domestic fixture calculations reuse one score matrix for outcome probabilities and score sampling/reporting. The matrix-to-outcomes helper preserves the original reduction and normalization order. UCL caches fixed outcome masks and xG availability dates without changing its probability arithmetic, temporal boundaries, or random draw order. Number-preserving cleanups are additionally checked against exact before/after frozen outputs, including match records, ratings, stakes, and the representative bracket; existing baselines are kept.

Domestic fixtures without quotes are essential: the current quoted-market blend nearly replaces the fitted team probabilities. A quoted-only case could pass while the goal/xG/Elo model was broken. UCL's archived market quotes influence strength fitting even when direct fixture-odds blending is disabled; cover that distinction explicitly.

Keep focused tests for exceptional rules, including awarded fixtures, temporal filtering, tie-breaks, and conditional stakes. A single numerical baseline need not exercise every exception.

## Configuration and provenance

Freeze the season, forecast origin, seed, simulation count, fixture/team order, score support, and every external input. Start with seed 7 and 10,000 simulations per case, then measure CI runtime before finalizing the fixture size.

Run with the actual production defaults. Record and compare the expected effective configuration alongside the baseline: calibration version and artifact hash, blend weights and their no-odds ratio, xG weight/scale, decay, regularization, and UCL offset/club/market/shift settings. Passing yesterday's hardcoded configuration would conceal a change to today's defaults. Fixtures and seeds are fixed; production settings are exercised and checked against their recorded expectations.

Protect production wiring too: either inject frozen loaders into the public forecast APIs or verify their resolved settings, CLI defaults, and daily command options against the expected configuration. Calling lower-level functions with `DEFAULT_*` alone would miss a production caller passing the wrong settings. Check the daily no-direct-odds behavior separately from the UCL archived-market fit, which remains enabled.

CI and daily refresh use Ubuntu 24.04, Python 3.12, one numerical worker thread, and the same pinned runtime dependencies. The existing NumPy pin requires Python 3.12; the former refresh workflow's Python 3.11 could not install this lock. Record the generating revision, Python/dependency versions, input hashes, and effective configuration with the baseline. Install the domestic and UCL packages for the test suite. Numerical dependency updates receive baseline review just like source changes.

Compare outputs by club, fixture identity, finishing position, and named metric. Preserve sampling order explicitly; do not rely on the display order of a sorted summary. Exclude generation timestamps, absolute paths, plots, HTML, and JSON byte formatting from numerical comparisons.

## Baseline comparisons and tolerances

Compare every fixture's home/draw/away probabilities, selected complete score distributions and goal rates, all clubs' finishing-position probabilities, expected points/position, and event probabilities. Include UCL advancement through to the title. Keep raw calculations separate from rounded site JSON.

The following absolute drift thresholds are enforced, with zero relative tolerance. Failures identify the club/fixture and metric and report its largest difference. They are review budgets, not guarantees of predictive accuracy.

| Quantity | Absolute tolerance | Unit |
| --- | ---: | --- |
| Deterministic outcome or scoreline probability | `0.000001` | Probability on 0–1 scale |
| Expected goal rate | `0.00001` | Goals |
| Simulated position, event, or stage probability | `0.1` | Percentage point on 0–100 scale |
| Simulated expected points | `0.01` | Point |
| Simulated expected position | `0.01` | Place |

At 10,000 simulations, 0.1 percentage point corresponds to ten simulated outcomes. This is a drift budget, not a confidence interval or a statement that a forecast is accurate to 0.1 point. With a fixed seed and fixed environment, ordinary rerun Monte Carlo noise is absent; changed numerical libraries or execution order can still change fitting and sampling.

The initial baselines were generated on macOS/Python 3.12 with the pinned numerical libraries; repeated public-API runs agreed exactly locally. The first Linux CI run must establish cross-platform compatibility. If it fails, inspect the differences rather than automatically widening tolerances. Future baseline updates should be generated and repeated in the canonical CI environment. A change that passes a tolerance can still be real, so configuration and structural invariants are checked separately.

For point quantiles, require finite, ordered, feasible bounds. If also comparing exact quantiles against a baseline, state the permitted movement explicitly: a discrete percentile can move by one point around a boundary. The expected points need not lie between the 10th and 90th percentiles.

## Invariants independent of the saved numbers

- Probabilities and goal rates are finite and in range; outcome triples and score distributions normalize to one. Score distributions preserve the blended home/draw/away masses.
- Each simulated club has one finishing position, and each position has one club. Position-matrix rows and columns sum to 100%; expected position is the probability-weighted position. Domestic title chance equals first-place chance; UCL league-phase first place is distinct from winning the tournament.
- Points and quantiles respect the current table, remaining fixtures, and any preserved deductions. Lower quantiles do not exceed upper quantiles.
- UCL top-eight, playoff, and eliminated chances partition 100% per club. Across clubs these conserve 8, 16, and 12 places; round of 16, quarterfinal, semifinal, final, and winner conserve 16, 8, 4, 2, and 1 places.
- UCL progression is nested: title ≤ final ≤ semifinal ≤ quarterfinal ≤ round of 16 ≤ top 24. A top-eight finish implies round-of-16 qualification.
- Repeating frozen inputs and configuration gives the same outputs within the declared tolerance.

Use tight floating-point allowances for raw conservation checks. Export rounding is governed by the data contract, not these regression budgets. Neither conservation nor a matching baseline proves that a football rule is implemented correctly; dedicated rule tests remain necessary.

## No network and temporal protection

Unexpected provider HTTP access must fail immediately. Tests must not depend on API keys, a populated developer cache, today's odds archive, or a live coefficient download. Currently the domestic `run_prediction` loads providers even without odds, and UCL `run_forecast(inputs=...)` still fetches coefficients. Inject or isolate those inputs, with a small refactor where that simplifies the shared production path.

Preserve and test the current timing rules rather than quietly standardizing them during this work:

| Path | Current eligibility rule |
| --- | --- |
| Domestic fitting | Result timestamp strictly before the reference date |
| UCL fitting | Result timestamp before origin; also `available_at < as_of` when supplied |
| Domestic fixture odds | `observed_at <= as_of` and observation strictly before kickoff |
| UCL archived fitting quotes | Observation strictly before both origin and kickoff |
| Domestic `--as-of` season rewind | Completed results count at kickoff plus three hours; live ingestion instead trusts the resolved provider status |
| Played-match refits | Reference time is 00:00 UTC on match day; domestic fitting uses earlier kickoffs, while UCL additionally masks xG where `normalize(kickoff) + 1 day >= origin` |
| UCL xG loading | Uses the same strict next-day masking: xG is eligible only when `normalize(kickoff) + 1 day < origin` |

With known schedules and identities held fixed, mutating excluded future result scores, unavailable xG, or ineligible quotes must leave the protected forecast unchanged. Changing known future fixtures can legitimately change a season forecast. Include an eligible-input perturbation that changes an appropriate output, so the fixture demonstrably exercises the input. A low-level fit/simulation regression alone does not test the rewind's three-hour delay or every played-match refit; keep those as focused boundary tests. These are descriptions of current semantics, not an endorsement that every boundary is ideal; any timing-policy change needs an explicit decision and revised tests.

## Reviewing a failure or changing a baseline

1. Check input hashes, configuration, dependencies, ordering, and the reported numerical differences. Determine whether the change is intended or a defect.
2. For a defect, fix the calculation; do not accept a new baseline just to make CI pass.
3. For an intentional change, include the reason, affected outputs, maximum movement, and any input/configuration change in the PR. A model-quality claim needs separate evaluation evidence.
4. Generate and review the new baseline in the canonical environment, then rerun regressions, invariants, and exporter/contract checks. CI never rewrites baselines automatically.

This suite does not validate provider freshness, future API compatibility, squad information, model uncertainty, browser rendering, or the site's JSON shape. Those require their own evidence or the publication contract below the model boundary.
