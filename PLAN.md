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

## Plan A: one-time global weight calibration

Goal: fit one set of blend weights (main / odds / Elo) and the xG weight on a decade of matches across Europe's main leagues, store it with the package, and use it as the fixed default for every competition. It is refit only by an explicit, versioned rerun, not per season or per forecast.

**Data (verified 2026-10-09).** For each league season, football-data.co.uk has results, pre-closing average/Pinnacle/Bet365 1X2 odds and, in recent seasons, closing odds (`…CH/CD/CA`). Its notes say pre-closing odds are "collected Friday afternoons" for weekend games and Tuesday afternoons for midweek games, so each quote gets an approximate observation time. Understat adds xG for the top five leagues from 2014/15.
- Calibration set: E0, SP1, D1, I1 and F1 for 2015/16–2025/26 (11 seasons, about 19,000 matches with xG and odds). 2014/15 serves as warm-up history.
- Robustness set: P1, N1, B1, T1, G1 and SC0 over the same years, without xG. It checks that the odds/model weights transfer to leagues outside the top five.

**Method.**
1. Build a rolling one-week-ahead dataset. For each league and match week, fit Dixon–Coles, Elo and xG strengths on results before that week's odds collection time (the preceding Tuesday or Friday, 00:00 UTC). Store `p_dc` for each xG weight in a grid {0, 0.25, 0.5, 0.75, 1}, plus `p_elo`, `p_odds` (average pre-closing, de-margined) and the outcome. Each fit happens once per league-week, which is cheap.
2. Fit the log-linear pool weights for main, odds and Elo by minimizing pooled log loss with nonnegative weights (scipy), separately for each xG grid value. Choose the xG weight with the lowest loss. For the rows without odds, which is most of a season simulation, the same weights renormalize over main and Elo; also report the loss for that case.
3. Check stability rather than tuning per league: leave-one-season-out and leave-one-league-out losses, weight spread across folds, and the robustness leagues. A fold whose weights move outside the spread is a warning, not an override.
4. Optionally include the decay `xi` and ridge `lambda_reg` in the same search (a small grid). Head-to-head stays at 0 unless it improves pooled loss.
5. Refit on all calibration data and write `src/standing_prediction/calibrated_weights.json` with the weights, data range, leagues, metrics, fold spread and code version. `DEFAULT_WEIGHTS`, `xg_weight` and the CLI defaults read from it, and forecast metadata records the calibration version.

**Deliverables:** `football-calibrate` (dataset build plus weight fit), the stored weights file, and a short report in this file. Every later forecast, including Champions League, uses these weights unchanged.

## Plan B: Champions League forecasts (league phase and knockout bracket)

**Format (2026/27 [regulations](https://documents.uefa.com/r/Regulations-of-the-UEFA-Champions-League-2026/27-Online)).** 36 teams, not 48. Each plays 8 league-phase matches (4 home, 4 away) in one 36-team table.
- Positions 1–8 go to the round of 16, 9–24 to two-legged knockout playoffs, and 25–36 are eliminated.
- Table order: points, then goal difference, goals scored, away goals scored, wins, away wins, then the opponents' collective points, goal difference and goals scored, then disciplinary points and club coefficient. Head-to-head is not used.
- Playoffs: 9/10 v 23/24, 11/12 v 21/22, 13/14 v 19/20, 15/16 v 17/18. Each seeded team's opponent is drawn from its pair, and the seeded team hosts the second leg.
- Round of 16: 1/2 v winners of the 15/16–17/18 ties, 3/4 v winners of 13/14–19/20, 5/6 v winners of 11/12–21/22, 7/8 v winners of 9/10–23/24. Each seeded pair is split by draw across the two halves of the bracket.
- Quarter-finals and semi-finals follow a fixed bracket. The better league-phase team hosts second legs. There are no away goals; level ties go to 30 minutes of extra time, then penalties. The final is a single match at a neutral venue.

**Data (verified 2026-10-09).**
- football-data.org `CL`: the 2026/27 table and all 144 league-phase fixtures (18 played), plus complete 2024/25 and 2025/26 seasons in the new format (league phase 144, playoffs 16, round of 16 16, quarter-finals 8, semi-finals 4, final 1). Scores include `regularTime`, `extraTime` and `penalties`. The free tier refuses seasons before 2023/24 (HTTP 403).
- Domestic leagues of the 36 teams: 18 play in the top five leagues (Understat xG plus football-data.co.uk). Another 14 are covered by football-data.co.uk results and odds: P1, N1, B1, T1, G1, plus `new/AUT` and `new/NOR`. Four teams have no free domestic data: Slavia Praha, Slovan Bratislava, Shakhtar and Sabah.
- Odds: The Odds API `soccer_uefa_champs_league` for scheduled fixtures; outright markets are an optional cross-check. ClubElo is not usable: its API returned HTTP 502 and its fixtures API is deactivated.

**Model.** The new piece is a common strength scale across leagues; everything else reuses current code.
1. **European Dixon–Coles:** one joint, time-decayed fit over all available domestic matches plus every Champions League match since 2023/24, using `regularTime` scores. Team attack/defense = league offset + team deviation. Deviations are shrunk toward their league offset rather than the global mean, so weak-league teams are not pulled up. League offsets are identified by cross-league European matches, with weak shrinkage. Teams without domestic data share an "other leagues" offset learned from their European results. European matches get their own home advantage. xG strengths blend into the deviation of top-five teams with the calibrated xG weight.
2. **Elo** over the same combined match stream; a new team starts at its league's mean rating.
3. **Blend** with the Plan A weights; odds apply wherever a fixture has a quote. The four teams without domestic data rely mostly on European results and odds, and their coverage is reported.
4. Optional: more cross-league links from Europa League and Conference League matches if a free, dated source is verified (for example openfootball); football-data.org's free tier excludes them.

**Simulator** (new module, reusing `build_fixture_specs` and vectorized scoreline sampling):
1. League phase: simulate the remaining scheduled fixtures and rank with the UEFA criteria above, including the opponent-strength criteria. Random order replaces the disciplinary and coefficient criteria, and this is labeled.
2. Draws: simulate the playoff draw within each seeded pair and the round-of-16 split across bracket halves. Once a real draw is published, use the actual pairings instead.
3. Two-legged ties: two scorelines at the correct venues (seeded team hosts the second leg). If the aggregate is level, extra time uses one third of the 90-minute rates at the second-leg venue; penalties are 50/50, configurable. The final is neutral. If a finalist plays at its own stadium, it gets home advantage; the 2026/27 venue still needs verifying.
4. Precompute blended score matrices for all 36×35 ordered pairs plus neutral pairs once per forecast, so knockout pairings decided during a simulation need no refits.

**Outputs:**
- A 36-position heatmap (same style as the league chart).
- Per team: expected points; P(top 8), P(9–24), P(eliminated); P(reaching the playoffs, round of 16, quarter-finals, semi-finals, final) and P(winning).
- Bracket views: the most likely playoff and round-of-16 pairings with their probabilities, and conditional advance probabilities once the draw is known.
- CSV/JSON/HTML plus snapshots, and a `football-ucl` CLI and notebook, as for leagues.

**Validation:** backtest 2024/25 and 2025/26 from origins after league-phase matchdays 2, 4, 6 and 8 and before each knockout round. Metrics: match log loss (also on the subset with odds), 36-position RPS, and stage-reach Brier scores. Compare the joint European model against a version that only uses domestic strengths with no league offsets, to show the cross-league scale is needed. Only two new-format seasons exist, so report these as checks, not tuning.

**Order:** Plan A first, because it fixes the weights. Then the European model and its match-level validation, then the league-phase simulator with the 2026/27 forecast, then knockout simulation, bracket outputs and backtests.

## Other existing priorities

Continue comparing baseline decay, priors, blend weights, and calibration; retain dated odds archives. Add dated disciplinary adjustments and deciding-playoff handling before claiming official-table equivalence. Keep conditional uncertainty and score-derived historical targets explicit. Tournament formats and larger model experiments remain outside this league-package plan.
