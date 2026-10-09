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
- Optional xG and predictive head-to-head (H2H) goal-rate adjustments (`xg_weight`, `h2h_weight`, both 0 by default), a `football-ablation` command that tunes them on earlier seasons and compares variants on later ones, and tests for prior-only features.

## xG and H2H: sources and design

Checked on **2026-10-09**:

| Source | Finding | Use |
| :--- | :--- | :--- |
| [Understat](https://understat.com/league/La_liga) `getLeagueData/<league>/<season>` | One provider for PL, La Liga, Bundesliga, Serie A and Ligue 1 from 2014/15. La Liga has 380/380 matches with xG in every season 2014/15–2025/26, and 69/69 so far in 2026/27. Kickoffs are UTC and match football-data.org exactly for 2026/27. Unofficial JSON endpoint without documented terms or versioning. | Sole xG source for every season, cached permanently for past seasons. |
| [football-data.co.uk](https://www.football-data.co.uk/spainm.php) `HxG`/`AxG` | Only in 2026/27, provider undocumented. Differs from Understat by a median of 0.25 xG per team per match (maximum 2.4), so it is a different model. | Not used; mixing providers would change the feature between seasons. |
| [FBref](https://fbref.com/) | Opta advanced data removed on 2026-01-20. | Not available. |
| [football-data.org](https://docs.football-data.org/general/v4/match.html) | No xG in the documented schema. `/head2head` returns aggregates for a single fixture. | H2H meetings come from dated result CSVs already used for history; no extra requests. |

**Joins:** home/away pairings are unique within a league season. A join also requires kickoff within two days (Understat's 2016/17 times are off by up to about a day) and an identical final score. For example, Union Berlin–Bochum 2024/25 was played 1–1 but awarded 2–0, so its xG is rejected. Unmatched rows keep missing xG, and coverage is written to metadata.

**xG model:** a time-decayed quasi-Poisson attack/defense fit to xG, centered and ridge-regularized. Its strengths blend with Dixon–Coles strengths, which equals the log-rate blend while keeping the goal model's intercept and home advantage. Teams without xG keep their goal strengths. Score matrices, outcome probabilities and scoreline sampling all use the adjusted rates.

**H2H model:** each meeting's goal difference minus a Dixon–Coles expectation fitted on the previous 730 days, with the model refitted every 28 days, so the baseline never sees that match or later ones. Pair effects pool venues, use a two-year half-life and shrinkage 4, and are filtered at the forecast origin. A fixture's log rates move by ±`h2h_weight × effect`. Simulated future meetings never feed back into the effect.

**Timing:** backtests assume Understat xG is published by the end of each match's UTC day. Historical publication times are not reconstructed, so xG comparisons are retrospective. Live forecasts save the joined xG with each matches snapshot for prospective checks.

## Ablation results (2026-10-09)

`football-ablation` was run with tuning seasons 2016/17–2019/20 and evaluation seasons 2020/21–2025/26. Each season was forecast at cutoffs after rounds 5, 10, 20 and 30 (24 snapshots per league), using 2,000 simulations, seed 7, team models only (no odds) and weights frozen after tuning.

| League | Variant | Weights (xG, H2H) | Match log loss | Position RPS | Exp. points MAE | Title / top-4 / bottom-3 Brier |
| :--- | :--- | :--- | ---: | ---: | ---: | :--- |
| La Liga | baseline | 0, 0 | 0.9917 | 0.0750 | 4.98 | 0.0197 / 0.0197 / 0.0740 |
| La Liga | xG | 0.5, 0 | **0.9859** | **0.0701** | **4.78** | 0.0184 / 0.0188 / 0.0711 |
| Premier League | baseline | 0, 0 | 0.9866 | 0.0727 | 6.02 | 0.0162 / 0.0656 / 0.0481 |
| Premier League | xG | 0.75, 0 | **0.9820** | **0.0710** | **5.87** | 0.0152 / 0.0620 / 0.0445 |

- **xG helps consistently.** In La Liga it improves match log loss in 21/24 snapshots and RPS in 23/24, and every evaluation season improves on average. In the Premier League it improves log loss in 18/24 and RPS in 16/24. Only 2021/22 is worse on average.
- **H2H adds nothing.** In both leagues, every positive weight raised tuning log loss, monotonically: La Liga 0.9706 → 0.9741 and Premier League 0.9484 → 0.9556 from weight 0 to 0.3. Tuning therefore selected 0, so the H2H-only and combined variants equal baseline and xG. H2H stays available but off.
- **Caveats:** snapshots within a season overlap; xG availability is assumed rather than reconstructed; odds were excluded. Live forecasts give odds 0.55 of the blend, and the market may already price in the xG information. No dated historical odds exist to test that.

**Next:** decide whether to make `xg_weight=0.5` the default for team-model rates; start collecting dated odds alongside the saved xG to test the odds interaction prospectively; optionally run the remaining three leagues.

## Other existing priorities

Continue comparing baseline decay, priors, blend weights, and calibration; retain dated odds archives. Add dated disciplinary adjustments and deciding-playoff handling before claiming official-table equivalence. Keep conditional uncertainty and score-derived historical targets explicit. Tournament formats and larger model experiments remain outside this league-package plan.
