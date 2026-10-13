> **Ignore for now.** These are deferred planning notes. Other agents should not read, use or implement this proposal during ordinary project work. Open it only when the user explicitly asks to inspect, edit or activate it. It does not change the active roadmap or authorize implementation.

# Expansion plan

Status: deferred. Written October 13, 2026, against repository revision `127df98`.

## 1. Goal and recommended approach

Add ATP and WTA singles predictions to Floodlight, starting with pre-match winner probabilities. Keep football behavior intact and reuse the project's experience with historical replay, calibration, market comparison and dated outputs.

Use a separate tennis package with its own data adapters, player ratings, parameters and evaluation. Share small utilities only when there is a clear second use. There is no need to redesign the whole repository into a generic sports framework before delivering a useful model.

The first release should answer: given two players, a surface, a match format and a forecast time, what probability does each player have of winning a normally completed match? State that target explicitly. Retirements and walkovers need their own recorded treatment; they must not silently become ordinary completed results.

Longer term, the same product can offer football and tennis forecasts through consistent navigation and reporting, while each sport retains the model and competition rules that fit it.

## 2. Scope

### First release

- ATP and WTA singles, initially main-draw tour events and Grand Slams with verified coverage.
- Separate men's and women's rating pools, hyperparameters and calibration, using the same code.
- Overall and surface-specific player ratings for hard, clay and grass courts.
- Match format awareness: best-of-three and best-of-five where applicable.
- Historical replay and proper probability evaluation before publishing current predictions.
- Current match forecasts, player ratings, source freshness and a transparent record of exclusions.
- A top-100 view per tour if useful, with broader opponent history retained underneath.

### Later milestones

- Opponent-adjusted serve/return strengths, rest and workload features.
- A head-to-head adjustment if it improves held-out predictions.
- Tournament progression and title probabilities after official draws are available.
- Set scores, game totals and other markets only after adding an appropriate scoring model.

### Outside the initial scope

Doubles, live point-by-point predictions, predicting future draws before entry lists exist, full ITF coverage, a combined cross-sport strength ranking, injury scraping, automated wagering and promises of beating bookmaker prices.

## 3. Current project foundation

The October 13 review found 72 existing tests passing. This verifies the current code's covered behavior; it does not validate a future tennis model.

| Existing area | Carry forward | Required change |
| --- | --- | --- |
| Dated input snapshots and forecast metadata | Provenance, reproducibility and forecast-origin discipline | Record tennis-specific dates, statuses and source versions |
| Historical match replay | Forecast from earlier information and score later results | Use match dates/round ordering rather than football matchdays |
| Global calibration package | Chronological holdouts, feature comparisons and versioned parameters | Separate tennis dataset and binary calibration; do not reuse football weights |
| Elo | Sequential strength updates and opponent comparisons | New binary model, surface state, inactivity handling and calendar-year semantics |
| Probability blending | Weighted blending of available predictions | Existing code returns three outcomes; adapt only if sharing is worthwhile |
| Odds archive | Observed-at timestamps, de-margining and immutable observations | Two outcomes, player identity mapping and tournament-specific sport keys |
| Champions League simulation | Experience conditioning on known draws and results | New singles draw logic; no football two-leg or extra-time rules |
| Website and refresh workflow | Static delivery, history and retaining old data after failures | Separate exports, player views and appropriate refresh frequency |
| Dixon–Coles, xG, league tables | Modeling and evaluation lessons | These models and ranking rules do not transfer directly |

Relevant code includes `src/standing_prediction/elo.py`, `ensemble.py`, `odds.py`, `match_forecasts.py`, `backtest.py`, the two existing packages, and `scripts/build_site_data.py`.

Current limits matter: model tests are not run by CI, the site has no enforced JSON schema, and the calibration feature format is football-specific. The football Elo code also assumes home advantage, draws and a July season boundary. These are reasons to isolate the new package and make small deliberate changes.

## 4. Data discovery is the first gate

Do not choose a model around an assumed data source. First prove that a usable historical dataset and a dependable current fixture/result feed can be obtained.

### Candidate sources and findings

| Source | Potential use | Finding on October 13, 2026 |
| --- | --- | --- |
| [TennisData.app downloads](https://tennisdata.app/downloads/) | Historical ATP/WTA matches and current-season results | Advertises 2021–2026, stable player IDs, main-tour/Challenger coverage and updates multiple times daily; downloads have a bot check. Files and automated access were not verified. Odds are usually closing prices. |
| [Sackmann's dataset announcement](https://www.tennisabstract.com/blog/2015/03/24/free-atp-and-wta-results-and-stats-databases/) | Long historical results, rankings and match statistics | The announcement documents extensive historical coverage. The linked ATP/WTA GitHub repositories and the checked ATP raw README returned 404. Do not assume these are currently available or maintained. |
| [Tennis-data.co.uk](https://www.tennis-data.co.uk/) | Historical results and bookmaker comparisons | Pages returned 403 through the browsing tool and the checked 2026 CSV URL returned 404. No working download or coverage was verified in this review. |
| [The Odds API](https://the-odds-api.com/) | Current and dated bookmaker probabilities | Official documentation advertises tennis coverage. The project already uses this provider, but event coverage and incremental quota costs need checking. |
| [Tennis API results](https://docs.tennis-api.com/results) and [fixtures](https://docs.tennis-api.com/fixtures) | Candidate current result/fixture feed | Documentation exists; account access, plans, actual coverage, historical depth and reliability remain unverified. |

These are candidates, not approved integrations. Recheck their current terms, permitted automated access and redistribution before selecting one. Do not bypass a bot check. Prefer one coherent source for results; add another only for a concrete gap.

### Discovery checklist

1. Obtain sample files for both tours, several completed seasons and the current season.
2. Measure coverage by year, tour, event level, surface, round, format and match status.
3. Check stable player IDs, name changes, missing fields, duplicate matches and corrections.
4. Verify whether dates represent the actual match day or only the tournament start. Determine the timezone and precision.
5. Verify where rankings, statistics and odds came from, and when they were observable.
6. Obtain upcoming fixtures and completed results through an allowed repeatable process. Confirm late schedule changes and cancellations are represented.
7. Record expected cost, quotas, refresh cadence, permitted public outputs and a practical fallback if the source fails.

**Exit condition:** select a source with reproducible sample ingestion and a written coverage/timing report. If only historical files are dependable, deliver the historical research milestone and defer the daily product.

## 5. Data contract and identities

Start with normalized tabular files and JSON outputs. A database is unnecessary for this scope.

### Minimum normalized records

| Record | Required information |
| --- | --- |
| Player | Internal ID, tour, display name, provider IDs and explicit aliases |
| Event | Internal/source ID, year, tour, event level, location, timezone, surface and indoor/outdoor when known |
| Match | Stable ID, event ID, round, player A/B IDs, best-of format, status, actual/scheduled date, time precision, winner and score when available |
| Result provenance | Source, source match ID, fetched-at time, result available-at time or its documented conservative approximation |
| Ranking observation | Player ID, ranking date, available-at time and rank/points where supplied |
| Odds observation | Match/player IDs, bookmaker, both decimal prices, observed-at time, scheduled start and source |

Add historical serve/return statistics only when used by an approved later feature. Keep the raw source payload or file hash so normalization can be audited.

### Normalization rules

- Use player IDs as keys. Football's `normalize_team` removes club-related words and is unsuitable as a player identity system.
- Treat A/B as arbitrary participant order, with no home advantage. Provider fields called `home`/`away` are labels, not a tennis advantage.
- Winner/loser source files must be converted to an orientation independent of the result, such as stable ID order. All features, scores and odds must follow that orientation.
- Do not expose outcome-dependent fields as pre-match inputs. Match duration and serve statistics can contribute only to later matches.
- A match can change scheduled time or player pairing. Reconcile provider IDs and retain the correction history; do not rely on names and date alone.
- Reject same-player matches, cross-tour singles pairings, duplicate conflicting results and impossible completed scores. Quarantine ambiguous rows and report them.
- Keep training history broader than the published top 100. Use rankings available at the origin for historical top-100 reports, rather than today's top 100.
- Use calendar years for tennis seasons. Do not reuse football's July rollover or season-dependent cache freshness without adaptation.

### Status policy

The initial model estimates normally completed match outcomes. Fit and primarily evaluate it on completed matches. Exclude walkovers and cancelled matches from rating updates. Record retirements/defaults separately and report their count and an official-winner sensitivity analysis; do not conceal exclusions.

If the product later targets official winners including retirements, make that an explicit target change with separate evaluation. Bookmaker settlement rules differ, so this proposal does not equate a sporting probability with a settled bet.

## 6. Timing and leakage prevention

All training features must be known at the forecast origin. Store event time separately from information availability and data retrieval time.

- With verified timestamps, update ratings only after a result is available.
- With actual match dates but no reliable times, forecast from the start of the day and make results available conservatively after that day ends in the documented timezone. Treat this as a historical approximation.
- With only tournament start dates, do not invent match dates or let later rounds train earlier rounds. Exclude the event from daily replay or use a separately labeled pre-tournament evaluation with frozen ratings and conditional pairings.
- Freeze predictions before updating on their outcomes. With ambiguous same-day order, keep ratings frozen for that whole group.
- Use ranking snapshots available before the origin. Current rankings and retrospective career summaries cannot initialize historical forecasts.
- Historical H2H features must stop before the target match, including their expected-outcome baselines.
- Closing odds can be a separately labeled near-start benchmark. They cannot be inputs or an equivalent information benchmark for an earlier daily forecast unless their observation time proves availability.
- Future draw pairings cannot appear as known fixtures before the draw or preceding results made them known.

Saved live forecasts should be immutable. A later historical replay belongs in a separate output, labeled retrospective, rather than replacing the published prediction.

## 7. First prediction model

### Baselines

Evaluate a 50/50 baseline, an as-of ranking-based probability model and ordinary overall Elo. Compare deterministic higher-ranked winner accuracy only as a secondary statistic; probability scores need actual probability forecasts.

### Overall and surface Elo

Maintain separate overall and surface ratings for every player in each tour. A simple initial effective rating is:

```text
effective_rating = overall_rating + alpha * (surface_rating - overall_rating)
P(A wins) = sigmoid(c_best_of * (effective_rating_A - effective_rating_B))
P(B wins) = 1 - P(A wins)
```

Here `alpha` is bounded between zero and one and shrinks toward zero when either player has little relevant surface history. `c_best_of` is a positive scale fitted for the match format. Start with a small parameter search and a fixed K per tour; only add a more elaborate update rule if evaluation supports it.

Use a symmetric format effect so swapping players complements the probability. An intercept based on arbitrary player order would be inappropriate. Fit format-specific scales only with enough evidence; otherwise use a pooled scale and mark sparse-format coverage.

Use historical ranking as a modest newcomer prior if it improves development results. Otherwise start at the tour mean and flag limited history. Carry ratings across January; do not copy automatic football season regression. Compare a simple inactivity regression to retaining the prior rating, and record time since last match.

Evaluate indoor/outdoor context after the base surface model. Grass has less evidence, so avoid independent grass parameters that produce unstable estimates.

### Calibration

Fit a small binary calibration layer on chronologically later development predictions, with symmetry preserved. Start with a single positive logit scale per tour if sufficient. Calibrate on predictions made without seeing their targets, not on in-sample fitted outputs.

Save each tour's parameters, feature definition, source hashes, training/calibration periods and model version in a separate artifact. Football's global blend, decay, ridge and xG settings have no authority here.

### Head-to-head experiment

Build H2H from the same dated match history; a separate H2H API is unnecessary. Displaying previous meetings and using them as a predictive feature are separate decisions.

For each past meeting, calculate the outcome residual against the baseline probability issued before that meeting. Aggregate residuals with recency weights, shrink toward zero, and test whether a surface-aware adjustment helps. Ensure the effect reverses when the player order reverses.

Start with H2H off. Select its weight on development seasons and retain it only for a repeatable improvement with acceptable calibration. Sparse pairs should fall back to the base prediction. Football's rejected H2H experiment is useful methodological experience, not evidence that the tennis effect must also be zero.

### Later features

Try one addition at a time: recent match workload, rest days, inactivity, indoor/outdoor context, then opponent-adjusted serve and return rates. Rank difference should not automatically be added on top of Elo without checking redundancy. Travel, altitude, court speed and injury data remain optional until a trustworthy source and measurable benefit exist.

## 8. Evaluation design

### Chronological protocol

Use rolling historical predictions and an untouched later period. Select model parameters, select optional features and fit calibration before examining the final holdout.

If verified data begins in 2021, a possible initial split is:

| Period | Role |
| --- | --- |
| 2021 | Rating warm-up |
| 2022–2024 | Model development with rolling internal validation |
| 2025 | Calibration from frozen-model pre-match predictions |
| 2026 through the recorded cutoff | Final evaluation; explicitly a partial season |

Adjust these dates to actual coverage before scoring. Ratings may update sequentially with earlier available holdout results, while hyperparameters and calibration stay frozen. Once holdout results influence a change, that period becomes development evidence; use a new future period for an independent assessment.

### Reports

- Primary metrics: binary log loss, Brier score with a documented convention, and calibration by probability bin with counts.
- Secondary metrics: winner accuracy and discrimination, alongside sample size and coverage.
- Splits: ATP/WTA, hard/clay/grass, format, season, event level, favorites/underdogs and limited-history players.
- Comparisons: ranking probabilities, overall Elo, surface Elo, calibrated model and de-margined market probabilities where available.
- Feature comparisons: surface, format, inactivity, H2H and any later feature, each against the same eligible matches.
- Uncertainty: paired loss differences with uncertainty grouped by tournament/time block, so matches within one event are not treated as entirely independent evidence.
- Data accounting: excluded statuses, unmatched players/odds, missing dates, source gaps and the exact forecast horizon.

Weight and report tours separately so one cannot hide the other's poor performance. Show pooled match-weighted results and surface splits; avoid claiming grass improvements from a tiny sample. Compare all models on the same quoted-match subset when assessing the market.

### Acceptance gates

Publish the surface model only if it improves development results over overall Elo consistently enough to justify the extra state. If the improvement disappears in the final holdout, keep the simpler model and report the result rather than tuning against the holdout.

Require valid, symmetric probabilities, acceptable calibration, documented coverage and honest treatment of sparse players. Record a minimum useful effect and uncertainty method before inspecting the final comparison. Beating bookmakers is not a release requirement, and importing odds cannot count as independent model skill.

## 9. Verification scenarios

Run the existing football suite around any shared-code change. Use small frozen input examples and repeatable offline checks for new behavior. Under the root Python rules, add automated Python tests only when explicitly requested; these scenarios define what must be verified, not permission to add tests.

1. Swapping players complements the probability and flips every oriented feature correctly.
2. Equal player states produce 50/50 probabilities. Every output is finite, bounded and sums to one.
3. Changing a future result cannot change an earlier rating, H2H feature or forecast.
4. Same-day matches with unknown order do not leak into one another.
5. A grass forecast with little grass history falls back toward overall strength.
6. A newcomer receives the documented prior and a history flag; no current-ranking lookup leaks backward.
7. Completed matches, retirements, defaults, cancellations and walkovers follow their declared policies.
8. Provider name variants resolve to one player; conflicting IDs/results are reported rather than guessed.
9. Future or stale odds do not enter a past forecast. Two-outcome quotes de-margin correctly.
10. Winner/loser source orientation does not reveal the target to the model.
11. A run at the same origin with identical inputs and parameters reproduces its predictions.
12. Football outputs remain identical on fixed inputs if shared utilities change.
13. A feed failure preserves the previous published tennis data and its original timestamp.
14. Exports load in the site with no empty required views, schema mismatch or console errors.

## 10. Package and output shape

Proposed layout once implementation is authorized:

```text
packages/tennis/
  pyproject.toml
  README.md
  src/tennis_prediction/
    data.py          # provider loading, normalized records and identity mapping
    ratings.py       # overall/surface Elo, priors and prediction
    evaluate.py      # chronological replay, calibration and reports
    cli.py           # historical evaluation and current forecasts
out/tennis/          # local experiments, normalized snapshots and reports
site/data/tennis/    # published outputs only after the release gate
```

This is a starting point, not a requirement to create empty modules. Add a separate odds or tournament module when that milestone needs it. Do not make the tennis package depend on football's goal model merely to reuse a few helpers. Small local implementations are acceptable until sharing clearly reduces duplication.

Current forecasts should expose: schema version, sport, tour, event/match IDs, player IDs/names, round, surface, format, status, scheduled time and its precision, forecast origin, two win probabilities, history/coverage flags, model version and source cutoff.

Export raw and calibrated model probabilities separately in evaluation data. If an odds-assisted forecast is later added, give it a separate field and record which observations it used. Omit unsupported scorelines and football goal fields entirely.

## 11. Daily operation and site integration

Add a separate refresh command and job after the model passes evaluation. Start with a daily forecast at a stated origin; increase frequency only if source availability and a clear product need justify it. Tennis schedules move and matches span timezones, so the current football refresh time must not silently define the new horizon.

Cache immutable historical files, refresh current data with suitable expiry, handle rate limits, and save inputs before prediction. Report stale/missing fixtures explicitly. Keep the existing football refresh independent so a tennis failure cannot block it.

Follow `DESIGN.md` and reuse the site's visual language. Provide a sport selector, ATP/WTA filters, upcoming/recent match probabilities and player rating views. Use two outcome bulbs and show surface, format, forecast time and freshness. Keep methodology on the Model view and link to it from forecasts.

Do not display tennis ratings as comparable to football club ratings. A top-100 player list can be the default view, with all covered opponents still represented in data and match pages. Keep pick accuracy secondary to the probability scorecard.

Before publishing, validate exporter/consumer agreement, check representative desktop/mobile views, and verify the complete path from source inputs to a displayed match and its subsequent recorded outcome. Routine daily refreshes must not refit calibration.

## 12. Tournament milestone

Start only after match probabilities and current data are dependable. The first deliverable is progression and title probabilities conditional on an official singles draw.

Support byes, qualifiers/unknown slots, withdrawals, replacements and known completed rounds. Use only draw information available at the origin. A fixed singles bracket can often be propagated exactly from pairwise probabilities; Monte Carlo is optional when extra uncertainty or conditional workloads justify it.

Keep player strength fixed within each simulated/probability-propagated tournament initially. Do not update Elo on imagined results. Handle format by event and round, and evaluate tournament forecasts issued before the event and before later rounds separately.

Report that title probabilities depend on the draw, entry information and fitted player strength. Unknown qualifiers need a documented prior or an explicit delayed forecast, rather than an invented named entrant.

## 13. Implementation sequence

| Milestone | Deliverable | Exit condition |
| --- | --- | --- |
| 0. Source audit | Sample ingestion, coverage/timing report, access/cost decision | Reproducible historical data; a verified plan for current data |
| 1. Offline baseline | Separate package, normalized results, overall/surface Elo and match probabilities | Deterministic historical predictions, status policy and leakage checks pass |
| 2. Evaluation | Frozen split, baselines, calibration and feature comparisons | A documented model choice supported by held-out evidence |
| 3. Current forecasts | Fixture/result ingestion, dated exports and failure handling | End-to-end repeatable refresh with trustworthy identities and freshness |
| 4. Site release | Match/player views and probability scorecard | Valid exports, reviewed browser behavior and preserved football behavior |
| 5. Tournament forecasts | Official-draw progression and title probabilities | Known results/slots respected and retrospective stage evaluation reported |
| 6. Optional research | Serve/return model or additional context | Repeatable improvement sufficient to justify complexity |

A rough effort estimate after finding usable data is several focused days for an offline baseline and a few weeks for a dependable daily product with evaluation and site integration. Source problems, historical date reconstruction and missing current coverage can dominate that estimate. The tournament and serve/return milestones are additional work.

## 14. Risks and decisions to settle at activation

| Risk or decision | Planned treatment |
| --- | --- |
| Historical source disappears or automation is unavailable | Verify retrieval first, retain permitted snapshots and avoid a daily-product commitment without a usable feed |
| Incomplete dates make replay optimistic | Preserve date precision, use conservative availability, separate tournament-origin evaluation or exclude ambiguous rows |
| H2H memorizes a few famous rivalries | Use prior-only residuals, shrinkage and a frozen feature comparison |
| Top-100 restriction loses useful opponents | Restrict the display, retain broader history and define historical cohorts as of the origin |
| Grass, newcomers or returning players have little evidence | Shrink toward overall/prior strength and expose history flags |
| Retirements distort the target | Declare the completed-match target, report exclusions and score an official-winner sensitivity separately |
| Market inputs conceal weak standalone predictions | Keep independent and odds-assisted outputs and evaluations separate |
| Provider identity or schedule corrections break joins | Stable IDs, explicit mappings, reconciliation and ambiguity reports |
| New work changes football behavior | Isolate the package and data paths; verify shared changes on fixed football inputs |
| An inspected holdout becomes a tuning set | Label it development evidence and reserve a later prospective evaluation |

At activation, settle the covered event levels, data source, publication target, forecast cadence and first milestone from the user's current request. The defaults in this proposal are recommendations and may be revised with evidence.

## 15. Research references

- [How well do Elo-based ratings predict professional tennis matches?](https://irep.ntu.ac.uk/id/eprint/42038/) — evidence for overall/surface Elo and separate ATP/WTA evaluation, with results from a limited set of Grand Slams rather than a guarantee for all events.
- [The Limited Value of Head-to-Head Records](https://www.tennisabstract.com/blog/2014/01/19/the-limited-value-of-head-to-head-records/) — historical analysis motivating caution about raw H2H records.
- [The Odds API market definitions](https://the-odds-api.com/sports-odds-data/betting-markets.html) — the `h2h` API market means match-winner odds; it is distinct from a historical head-to-head feature.
- The active repository's `README.md`, package READMEs, `PLAN.md` and `ROADMAP.md` — existing modeling experience and documented limitations. Recheck these against current code before implementing.

No implementation, provider purchase, workflow change, deployment or calibration rerun is authorized by saving this plan.
