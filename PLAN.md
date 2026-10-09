# Package plan: xG and predictive head-to-head

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

## Proposed next work

Draft only: add optional xG and predictive head-to-head (H2H) adjustments to the existing goal model. Keep both disabled until chronological comparisons support them. Reuse existing sources first; a new provider is not required to start inspecting and collecting the current CSV fields.

The model's `expected_goals()` returns predicted scoring rates from historical goals. Observed shot-based xG measures the chances created during a completed match; these are separate inputs. H2H here means a possible predictive matchup effect. La Liga's H2H ranking rules are already implemented and remain independent of this experiment.

## 1. Verify and retain existing source data

Checked on **2026-10-09** against official documentation and live CSV contents:

| Existing source | Verified capability | Planned use |
| :--- | :--- | :--- |
| [football-data.org v4](https://docs.football-data.org/general/v4/match.html) | Dated scores, match/team IDs, and a documented `/matches/{id}/head2head` resource. The documented match schema has no xG field. Its [January 2026 announcement](https://www.football-data.org/blog) mentions forthcoming xG, without establishing our account's current access or schema. | Keep it as the live schedule/standings/results source. Inspect actual responses for documented or confirmed xG support; prefer already loaded results for H2H rather than extra requests. |
| [football-data.co.uk La Liga CSVs](https://www.football-data.co.uk/spainm.php) | The [2026/27 CSV](https://www.football-data.co.uk/mmz4281/2627/SP1.csv) has `HxG`/`AxG`, populated for **69/69** completed matches, dated **Aug 15–Sep 20, 2026**. The [2024/25](https://www.football-data.co.uk/mmz4281/2425/SP1.csv) and [2025/26](https://www.football-data.co.uk/mmz4281/2526/SP1.csv) files each have 380 results and no xG columns. | Preserve the current optional fields. Existing result histories already supply H2H encounters. The CSV currently extends no later than the API's September 20 result cutoff. |
| [CSV field notes](https://www.football-data.co.uk/notes.txt) | Define results and shots (`HS`, `AS`, `HST`, `AST`), but do not define `HxG`/`AxG` or their underlying provider. | Confirm xG provenance and meaning before enabling it. If absent, shots may support a separately labeled shot-form experiment; they are not shot-based xG. |
| [The Odds API soccer feed](https://the-odds-api.com/sports-odds-data/epl-odds.html) | `h2h` is the home/draw/away **1X2 betting market**, not previous encounters. Its current odds endpoint does not supply observed xG. | Continue timestamped bookmaker blending. Do not treat odds market names as H2H history or infer observed xG from 1X2 prices. |

Before model use, establish whether `HxG`/`AxG` are post-match pre-shot xG, their provider/model version, penalty treatment, match duration, publication timing, and revision policy. A field name and plausible numeric values do not establish these properties. Keep unknown provenance explicit and inspect season/league coverage rather than assuming historical backfill.

Minimum retained match record: competition/season, source match ID where available, kickoff UTC, canonical home/away teams, integer goals, separate nullable **float** `home_xg`/`away_xg`, provider/metric scope, first-seen or published timestamp, retrieval timestamp, and raw snapshot reference. Missing xG stays missing; do not substitute zero or scored goals. Preserve source versions when values change.

The existing `fetch_football_data_uk_matches()` in `odds.py` drops xG columns. Retaining them is only the first step: current forecasts obtain completed matches from football-data.org, while `load_season_results()` currently supplies historical/calibration results. Explicitly load the current-season CSV and join its optional xG into API completed matches. Match competition/season, normalized team pairs, and kickoff date in a consistent timezone; check both final scores. Prefer IDs/exact kickoff where available. Reject ambiguous joins and report mismatches/coverage rather than silently assigning values.

## 2. Add a small xG rate adjustment

Fit an optional, time-decayed attack/defense model to validated historical xG totals, accounting for opponent and home advantage. Use centered strengths and regularization toward league average, especially with only 69 observed matches. A continuous-response log-link/quasi-Poisson objective can estimate these means without treating fractional xG as integer goals.

Retain the existing Dixon–Coles likelihood on integer `homeGoals`/`awayGoals`. For each fixture, combine its goal-based rate with the xG-based rate through one shared, regularized weight:

```text
log(new_rate) = (1 - w_xg) * log(goal_based_rate) + w_xg * log(xg_based_rate)
```

Start at `w_xg = 0`; select it on earlier validation data. Check systematic provider/penalty-scope differences before interpreting xG rates as total goal rates. Missing or insufficient xG history falls back to the goal baseline, with coverage recorded.

Use the adjusted rates consistently for the Dixon–Coles score matrix, outcome probabilities, and conditional score sampling. Then apply the existing Elo/odds blend. This allows the added information to affect both points and goal-based tiebreaks. Keep one shared feature path for prediction and backtesting; avoid separate notebook logic or a large new model family.

## 3. Evaluate a strongly shrunk H2H residual

Build past encounters from current and prior-season score rows in both home/away directions. Fetch `/head2head` only if needed to fill a verified gap; use dated individual matches and filter them at the forecast origin, rather than trusting a current aggregate in a historical backtest.

Measure what previous meetings showed **beyond ordinary team strength**. For teams A and B, orient each past encounter as A minus B:

```text
residual_j = actual_goal_difference_j - baseline_expected_goal_difference_j
pair_effect = sum(recency_weight_j * residual_j) / (shrinkage + sum(recency_weight_j))
```

Historical baseline predictions must come from rolling, prior-only fits available before each encounter. Otherwise the residual can absorb future information or reflect a model already fitted to that result. Begin with one shared coefficient adjusting the two log goal rates in opposite directions; regularize it toward zero. No prior encounters means zero adjustment.

Pool venues initially while the historical baseline accounts for home advantage. Compare a same-venue weighting variant only if supported by validation. Downweight old meetings, report effective sample size, and shrink heavily: two league meetings per year leave very little evidence, while squads/coaches change. Raw win-count boosts would largely repeat the strength information already in Dixon–Coles/Elo.

For a whole-season forecast, construct this feature from information available at its origin and keep it fixed within that forecast. Simulated future meetings are not observed evidence. The separate simulated H2H statistics used for ranking still update normally.

## 4. Preserve timing and validate before changing defaults

- Build each feature only from completed matches whose relevant data was available by that forecast origin. Record publication/first-seen and retrieval times separately. A live forecast origin must follow input collection; later retrieval does not prove availability at a past cutoff.
- For old backfilled xG without publication history, label comparisons as retrospective with an explicit availability assumption. Do not describe them as fully reconstructed historical snapshots. Keep saving raw observations now for prospective evaluation.
- Compare **baseline**, **xG only**, **H2H only**, and **both**, using identical chronological origins, simulations/seeds, and source coverage. Tune decay, shrinkage, and coefficients on earlier data; freeze them before evaluating later seasons.
- Report match log loss/Brier, final-position RPS, expected-points error, and title/top-four/bottom-three Brier. Compare the same matches with and without odds and on their common covered subset: market probabilities may already reflect the added information. Overlapping horizons are not independent observations.
- Current CSV coverage supports ingestion and a prospective experiment, but not a multi-season xG comparison. Seek confirmed same-source backfill; otherwise collect later data and keep xG experimental. Promote neither feature on one partial season or an in-sample gain. H2H may reasonably remain disabled if its residual adds no consistent value.

Deliverables for a later implementation: optional retained/joined xG data and coverage metadata; a small shared rate-adjustment layer; optional xG/H2H flags; and an ablation report. No feature implementation, provider subscription, or default change is part of this draft.

## Other existing priorities

Continue comparing baseline decay, priors, blend weights, and calibration; retain dated odds archives. Add dated disciplinary adjustments and deciding-playoff handling before claiming official-table equivalence. Keep conditional uncertainty and score-derived historical targets explicit. Tournament formats and larger model experiments remain outside this league-package plan.
