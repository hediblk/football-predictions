# Football forecasting plan

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
- xG and predictive head-to-head (H2H) goal-rate adjustments, a `football-ablation` command that tunes them on earlier seasons and compares variants on later ones, and tests for prior-only features. xG now uses the stored global default; H2H remains off.
- Separately installable `packages/forecast-calibration`, with `football-calibrate`, pooled league-season weighting, chronological holdout and leave-out checks, external robustness leagues, and versioned defaults included with `standing_prediction`.

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
- **Caveats:** snapshots within a season overlap; xG availability is assumed rather than reconstructed; odds were excluded. These experiments preceded the global calibration below, which now supplies the defaults. That calibration uses approximate historical quote times; prospective timestamped odds archives remain necessary for exact live-forecast comparisons.

## Plan A: one-time global weight calibration (implemented)

Goal: fit one set of blend weights (main / odds / Elo) and the xG weight on a decade of matches across Europe's main leagues, store it with the package, and use it as the fixed default for every competition. It is refit only by an explicit, versioned rerun, not per season or per forecast.

**Data (verified 2026-10-09).** For each league season, football-data.co.uk has results, pre-closing average/Pinnacle/Bet365 1X2 odds and, in recent seasons, closing odds (`…CH/CD/CA`). Its notes say pre-closing odds are "collected Friday afternoons" for weekend games and Tuesday afternoons for midweek games, so each quote gets an approximate observation time. Understat adds xG for the top five leagues from 2014/15.
- Calibration set: E0, SP1, D1, I1 and F1 for 2015/16–2025/26 (11 seasons, about 19,000 matches with xG and odds). 2014/15 serves as warm-up history.
- Robustness set: P1, N1, B1, T1, G1 and SC0 over the same years, without xG. It checks that the odds/model weights transfer to leagues outside the top five.

**Method.**
1. Build a rolling one-week-ahead dataset. For each league and match week, fit Dixon–Coles, Elo and xG strengths on results available before that week's approximate odds collection time (the preceding Tuesday or Friday, 00:00 UTC). Results and xG become available the next UTC day after the local match date; unknown kickoffs use a noon UTC anchor. Store `p_dc` for each xG weight in a grid {0, 0.25, 0.5, 0.75, 1}, plus `p_elo`, `p_odds` (average pre-closing, de-margined, Bet365 fallback) and the outcome. Each fit happens once per league-week.
2. Fit nonnegative log-linear pool weights with scipy, separately for each xG grid value. Every league-season contributes equally; the objective averages log loss with odds masked and log loss on rows with quotes. This estimates the main/Elo ratio for unquoted future fixtures alongside market share for quoted fixtures. Choose the xG weight with the lowest combined loss. Market weight is capped at `1 - 1e-6` so the main/Elo renormalization remains defined.
3. Hold out the latest two seasons chronologically before refitting all data. Check stability with leave-one-season-out and leave-one-league-out losses, weight spread across folds, and the robustness leagues. Fold variation is reported, without per-league overrides.
4. Keep decay `xi=0.003`, ridge `lambda_reg=0.1` and up to two prior seasons fixed for this run. A future version may search decay and ridge explicitly. Head-to-head stays at 0.
5. Refit on all calibration data and write `src/standing_prediction/calibrated_weights.json` with the weights, data range, leagues, metrics, fold spread and code version. `DEFAULT_WEIGHTS`, `xg_weight` and the CLI defaults read from it, and forecast metadata records the calibration version.

**Deliverables:** `football-calibrate` (dataset build plus weight fit), the stored weights file, and a short report in this file. Every later forecast, including Champions League, uses these weights unchanged.

### Calibration results (2026-10-10)

Implemented in the separate [forecast-calibration package](packages/forecast-calibration/README.md), with artifact `src/standing_prediction/calibrated_weights.json`, version **`global-8c8185b60bc9`**. The run contains **19,763** unique calibration fixtures across five leagues and 11 seasons, plus **18,490** fixtures in six external leagues. Pre-closing odds cover 19,762 calibration fixtures; Understat xG matches 19,759, with four score/date mismatches rejected. Provider spelling fixes recovered 238 additional xG joins.

Final defaults: **xG weight 0.75**; **main 81.74%, Elo 18.26% when odds are absent**. With odds present, the fitted market share reaches the 99.9999% cap, so quoted outcome probabilities effectively follow the market. This is the fitted result, rather than a prescribed three-way blend. H2H remains 0. Forecasts load these settings and record the version; only an explicit calibration rerun replaces them.

The chronological check fitted weights on 2015/16–2023/24, then froze them for **3,504 matches in 2024/25–2025/26**. Its no-odds ratio was 80.36% main / 19.64% Elo, independently of the final all-data refit. Log loss uses equal league-season weights; lower is better:

| Forecast | Previous defaults | Frozen fit |
| :--- | ---: | ---: |
| Without odds | 0.99472 | **0.98679** |
| With pre-closing odds | 0.97831 | **0.97100** |

All 16 leave-out folds selected xG weight 0.75 and improved no-odds loss over the previous defaults. The fitted main share without odds ranged from **79.56% to 84.03%**. These folds measure stability; the chronological comparison above is the check on later seasons.

**Transfer limitation:** without xG or odds, external-league loss worsened slightly in all six leagues (0.00007–0.00062). With odds it improved in all six (0.00338–0.00621). The same global weights remain in use; these checks do not establish universal optimality. Quote collection and xG publication times are approximate, and match-level improvements do not establish calibrated long-horizon standings probabilities.

## Plan B: Champions League forecasts (league phase and knockout bracket)

**First version implemented; researched 2026-10-10.** The separate [Champions League package](packages/champions-league/README.md) exports the league-phase heatmap, qualification/title probabilities and a projected knockout bracket, now shown in the README. The design below is retained as the implementation record; current coverage and verification results follow it. The calibrated model weights remain unchanged. UCL forecasts run **without odds by default**. A quote remains an optional adjustment for that particular fixture, not a requirement for forecasting the tournament. The existing league predictor's defaults are unchanged.

### Competition rules

- **League phase:** 36 clubs, eight different opponents each, four matches at home and four away, one table and 144 fixtures. Positions 1–8 enter the round of 16; 9–24 enter the knockout playoffs; 25–36 are eliminated. [UEFA Article 17](https://documents.uefa.com/r/Regulations-of-the-UEFA-Champions-League-2026/27/Article-17-Match-system-league-phase-Online)
- **Ranking:** points, goal difference, goals scored, away goals scored, wins, away wins, opponents' collective points, opponents' collective goal difference, opponents' collective goals scored, lower disciplinary points, then higher club coefficient. Head-to-head is absent. Opponent totals must come from each simulated final table. [Article 18](https://documents.uefa.com/r/Regulations-of-the-UEFA-Champions-League-2026/27/Article-18-Equality-of-points-league-phase-Online)
- **Playoff draw:** 9/10 v 23/24, 11/12 v 21/22, 13/14 v 19/20, 15/16 v 17/18. The seeded clubs host the second legs in principle. Round-of-16 seeds 1/2 face winners from 15/16–17/18, 3/4 from 13/14–19/20, 5/6 from 11/12–21/22, and 7/8 from 9/10–23/24. Draws assign clubs to their allowed bracket slots; same-country opponents and repeat league-phase meetings are allowed. [Article 19](https://documents.uefa.com/r/Regulations-of-the-UEFA-Champions-League-2026/27/Article-19-Draw-system-knockout-phase-Online)
- **Later rounds:** use the fixed bracket. Ranks 1–4 have second-leg home priority in the quarter-finals; ranks 1–2 have it in the semi-finals. An upset winner inherits the eliminated seed's bracket position and priority. Do not rerank surviving clubs. Round-of-16 seeds also host their second legs in principle. [Article 19.04](https://documents.uefa.com/r/Regulations-of-the-UEFA-Champions-League-2026/27/Article-19-Draw-system-knockout-phase-Online), [Annex B](https://documents.uefa.com/r/Regulations-of-the-UEFA-Champions-League-2026/27/Annex-B-UEFA-Champions-League-Competition-System-Online)
- **Resolving ties:** playoffs through semi-finals have two legs, decided on aggregate, without an away-goals rule. A level aggregate goes to 30 minutes of extra time at the second-leg venue, then penalties. The final is one match, with extra time and penalties if required. [Article 20](https://documents.uefa.com/r/Regulations-of-the-UEFA-Champions-League-2026/27/Article-20-Match-system-knockout-phase-Online), [Article 21](https://documents.uefa.com/r/Regulations-of-the-UEFA-Champions-League-2026/27/Article-21-Knockout-system-extra-time-and-penalty-shoot-outs-Online), [Article 22](https://documents.uefa.com/r/Regulations-of-the-UEFA-Champions-League-2026/27/Article-22-Match-system-final-Online)
- **2026/27 final:** Madrid's Estadio Metropolitano, 5 June 2027. Use neutral match rates initially; an Atlético stadium-effect sensitivity would be an explicit modeling choice, not automatic home advantage from the nominal home designation. [UEFA final announcement](https://www.uefa.com/uefachampionsleague/news/029d-1eb2d5faf53c-d67c9fed04fa-1000--2027-uefa-champions-league-final-estadio-metropolitano/)

### Available data

Live football-data.org API checks returned **144 fixtures, 18 finished and 126 scheduled** for 2026/27, with all 36 clubs on **one UCL match played**. Matchday 2 is 13–14 October, so current domestic results and prior seasons are essential; one European game per club is insufficient to estimate strength. [UEFA season dates and participants](https://www.uefa.com/uefachampionsleague/news/02a6-20d57cfcd03e-407c22a7f465-1000--2026-27-champions-league-teams-dates-draws-format-final/)

The same API returned all **125 finished matches in 2023/24**, **189 in 2024/25** and **189 in 2025/26**. Each new-format season contains 144 league matches, 16 playoff legs, 16 round-of-16 legs, eight quarter-final legs, four semi-final legs and one final. Earlier seasons are outside the verified free-tier access. Retain raw stage, match ID, kickoff, venue and score-period fields. [API match schema](https://docs.football-data.org/general/v4/match.html)

**Domestic coverage:** 21 clubs play in England (5), Spain (5), Germany (4), Italy (4) and France (3), where the existing results and Understat xG adapters apply. The other **15 clubs** have the following results sources; none has verified xG from our existing provider:

| League | UCL clubs | Source and audit result |
| :--- | :--- | :--- |
| Portugal | Sporting, Porto | [P1 CSV](https://www.football-data.co.uk/mmz4281/2627/P1.csv): seven finished games per club. |
| Netherlands | PSV, Feyenoord | [N1 CSV](https://www.football-data.co.uk/mmz4281/2627/N1.csv): seven each. |
| Belgium | Club Brugge | [B1 CSV](https://www.football-data.co.uk/mmz4281/2627/B1.csv): seven. |
| Turkey | Galatasaray, Fenerbahçe | [T1 CSV](https://www.football-data.co.uk/mmz4281/2627/T1.csv): six each. |
| Greece | AEK | [G1 CSV](https://www.football-data.co.uk/mmz4281/2627/G1.csv): five. |
| Austria | LASK | [AUT CSV](https://www.football-data.co.uk/new/AUT.csv): seven; filter season 2026/27. |
| Norway | Bodø/Glimt, Viking | [NOR CSV](https://www.football-data.co.uk/new/NOR.csv): 21 each; calendar season 2026. |
| Czech Republic | Slavia Praha | [Pinned openfootball source](https://github.com/openfootball/europe/blob/0bf83f88e8feb22904c5f9d93c6407574c1347e0/czech-republic/2026-27_cz1.txt): 71 scored fixtures, nine for Slavia; needs a football.txt adapter. |
| Slovakia | Slovan Bratislava | [Official results](https://www.nikeliga.sk/zapasy): current results and season selectors back through 2012/13 are accessible; needs an HTML adapter and completeness checks. |
| Ukraine | Shakhtar | [Official UPL calendar](https://upl.ua/en/tournaments/championship/432/calendar): dated current results; selectors include 2025/26 and 2024/25. Needs an HTML adapter, limited to the senior league. |
| Azerbaijan | Sabah | [Official PFL seasons API](https://pfl.az/api/v1/seasons?project_id=1) lists current and prior seasons. Its [current games API](https://pfl.az/api/v1/tours/get-games?league_id=52&withGames=true) returns dated scores and statuses: 38 finished fixtures, six for Sabah. Needs a small adapter; discover league IDs from seasons rather than hardcoding them. |

The seven extra-league CSVs and Czech file above stopped at **20 September** when audited on 10 October. Show each source's latest result and every club's match count; source availability does not establish freshness or completeness. Norway's calendar-season history must be selected by dates. The four country adapters are now implemented, with historical reconciliation and remaining gaps reported in the implementation snapshot below. Current official sources mean these clubs need not be classified as having no domestic data.

For cross-league links beyond UCL, [openfootball's European competitions repository](https://github.com/openfootball/champions-league/tree/abfaeddc2ee3d14f99ecc163c9ddb46cb4d67cef) contains scored 2024/25 Europa League and Conference League files, plus some later qualifying files. This is useful supplementary history, not verified complete 2025/26–2026/27 coverage. Ingest only audited files, preserve the commit SHA and correctly parse extra-time notation. Do not make a paid provider, ClubElo or bookmaker coverage a dependency.

### Data and strength model

Reuse the installed `standing_prediction` model, xG, blending and score-sampling code. Put UCL ingestion, joint strengths and tournament logic in a small separate `packages/champions-league` package depending on it, with `football-ucl` as its entry point. Do not copy the existing league implementation or change its behavior.

1. **Normalize and audit inputs.** Map provider club IDs and aliases explicitly, and record the domestic league associated with each match. Load full domestic leagues, including opponents outside the UCL field, current results and up to two prior seasons. Add the available dated European history and filter every source strictly before the forecast origin. Deduplicate overlapping European sources. Cache raw responses and store origin, source versions, coverage and freshness in forecast metadata.
2. **Use 90-minute scores.** On API games with `duration=REGULAR`, use `fullTime`; on extra-time or shootout games, require `regularTime`. The existing league `_matches_to_df` cannot be reused blindly: for example, Liverpool–PSG in March 2025 has API `fullTime=1–5`, but `regularTime=0–1` and penalties 1–4. Extra-time and penalty scores belong in tie state, not the 90-minute goal fit. Verify neutral venues for historical finals and relocated home games separately.
3. **Put leagues on a common scale.** Fit one time-decayed Dixon–Coles model over the combined stream. Domestic attack/defense deviations describe a club relative to its league; European matches estimate the strength differences between leagues. A minimal identifiable formulation uses one league-strength offset, added to attack and subtracted from defensive weakness, so it cancels in domestic games. Center team deviations within each league, fix one reference league offset, and use separate domestic and European scoring/home baselines. Regularize sparse estimates and audit the graph of European links. Equal domestic win rates must not imply equal international strength.
4. **Apply xG where observed.** Blend top-five domestic team deviations with their centered Understat xG deviations using the saved **0.75** weight, retaining the European league offsets and baselines. Clubs without xG retain their goal-based deviations; do not fill xG with zero or mix unvalidated providers. Missing domestic histories require an explicit European-results fallback and coverage flag, not a shared strength offset for unrelated countries. Sparse countries need prior-sensitivity reporting before presenting their title probabilities as reliable.
5. **Keep Elo on the same connected stream.** Process domestic and European results chronologically. New clubs start from a league center estimated from earlier European evidence, with season regression. A joint Elo stream alone does not solve disconnected league ratings; report sparse links and verify international match predictions.
6. **Keep the global blend fixed.** Without odds, use **81.74% main / 18.26% Elo**, H2H off, and calibration version `global-8c8185b60bc9`. Reuse the saved artifact rather than rounding these values in code. Optional timestamped 1X2 quotes affect only matching fixtures and expire; missing quotes use the normal no-odds blend. These weights were validated on domestic matches, so European validation remains necessary.

### Tournament simulation

1. **Condition on observed results.** Keep played scores fixed; simulate only future fixtures. Add a UCL validator: 36 clubs, eight distinct opponents and four home/four away games each, 144 unique league fixtures, with played totals matching official standings. The existing double-round-robin validator is unsuitable.
2. **Finish and rank the league phase.** Compute all sporting tiebreakers, including opponents' collective totals, within each simulation. Load the season's club coefficients. Future disciplinary points are not currently modeled; if they decide a tie, use a seeded random fallback before the coefficient criterion and report its frequency. This is an approximation, not official-table equivalence. Once the league phase is complete, use official final ranks.
3. **Draw the allowed bracket.** Before draws, sample permitted playoff and round-of-16 slot assignments; do not sample unrestricted opponents or reseed later rounds. Once real pairings and venue order are published, condition on them. Represent later home-leg priority as an attribute of the seeded bracket slot, inherited after an upset.
4. **Play each tie.** Sample two venue-correct 90-minute scorelines, combine the aggregate, then resolve extra time and penalties if required. After a played first leg, fix its score and simulate only the return leg. Initially use one third of the second-leg goal rates for extra time and a 50/50 shootout. These are explicit approximations; future tactical responses to aggregate score are outside the first version. Use neutral rates in the single-match final.
5. **Reuse score distributions.** Precompute possible ordered and neutral matchups once per forecast, then simulate brackets without refitting strengths on simulated results. Stage probabilities describe match/draw randomness conditional on fitted strengths; Monte Carlo error does not include uncertainty in the strength estimates.

### Outputs and implementation order

Deliver a 36-position heatmap and a table with expected league points, P(top 8), P(9–24), P(league-phase elimination), and probabilities of reaching each knockout round and winning. Export CSV/JSON/HTML, input snapshots and calibration/rule versions. Label P(entering playoffs) separately from P(reaching round of 16), since the top eight bypass playoffs. Add pairing/bracket views after the basic probabilities work.

1. **Data first:** existing sources plus the four missing domestic adapters; reconcile identities, 90-minute scores, current freshness, history and league-phase fixtures. Produce a coverage report for all 36 clubs before a forecast.
2. **Strengths second:** fit the common European scale and check held-out international match log loss against the same model without league offsets and a simple joint-Elo baseline. Freeze the global blend and xG weights. Use a goals-only comparison to measure the effect of uneven xG coverage.
3. **League phase third:** implement the schedule/ranking rules and publish the current 2026/27 league-phase forecast.
4. **Knockouts fourth:** implement the bracket, inherited home priority, aggregate state, extra time and penalties; export stage and title probabilities.
5. **Historical checks:** replay 2024/25 and 2025/26 after matchdays 2, 4, 6 and 8 and before knockout rounds, with strictly earlier data. Use each season's actual rules, draws and final venue; do not apply the newer home-priority rule retroactively. Report match log loss, position RPS and stage-reach Brier scores, including results split by xG coverage. Check probability conservation (eight direct qualifiers, eight playoff winners, 16 round-of-16 entrants, eight quarter-finalists, four semi-finalists, two finalists, one champion). Two seasons provide limited tournament-level evidence, so avoid tuning repeatedly against their winners.

First-version scope: a dated forecast from the current league phase through the final, using the fixed weights and available observed matches. No live in-play model, transfer/injury model, new weight search or paid-data integration.

### Implementation snapshot (2026-10-10)

`football-ucl --season 2026 --as-of 2026-10-11T01:30:00Z --n-sim 10000` generated the committed README charts and CSV/JSON snapshots. It conditions on **18 completed league-phase fixtures**, fits **11,165 domestic/European results** across 40 explicitly identified leagues, and uses **3,777 matched xG observations**. Every current UCL club has domestic history. The European link graph is connected, but six current leagues have sparse effective links; the forecast repeats offset shrinkage at 1, 4 and 16 and exports the resulting title-probability ranges.

The current title favorite is **Bayern München, 18.99%** (Monte Carlo standard error **0.39 percentage points**, conditional on fitted strengths). Its illustrative bracket also ends with Bayern winning; the bracket follows one permitted draw and matchup favorites rather than representing the most probable complete tournament outcome.

The four domestic adapters are implemented. Official Slovak and Ukrainian tables reconcile across the loaded seasons; Azerbaijani checks retain a 2025/26 fixture/table score discrepancy. The pinned Czech source lacks 2025/26. Current top-five, Portuguese and Dutch API results refresh stale CSVs, while several other current domestic sources still stop on September 19–20. Raw responses, identities, normalized inputs, per-club counts, freshness, source pins and these discrepancies are preserved. The official UEFA coefficient feed returned HTTP 403; no coefficients are invented. Simulated discipline ties use the documented random fallback before coefficients, with **0.00%** of current simulations requiring it; complete league phases use official final ranks.

The inherited quarter-/semi-final second-leg priority was introduced in **2025/26**, already before the current season, as confirmed by [UEFA's 2025/26 format explainer](https://www.uefa.com/uefachampionsleague/news/0296-1d21e9bdf7e4-808a7511165c-1000--2025-26-champions-league-format-dates-draws-final/). Historical 2024/25 simulations use the earlier venue-order rule. Relocated Shakhtar, Dynamo Kyiv and Maccabi Tel-Aviv European homes, plus Beşiktaş–Maccabi in Debrecen, use flagged neutral rates. Future knockout participants are hidden until earlier rounds resolve and draw dates permit them; result/xG availability is filtered strictly at each origin. These are retrospective availability approximations.

**Historical replay:** all **18 origins** in 2024/25 and 2025/26 completed with 2,000 simulations and seed 7: after MD2/4/6/8 and before playoffs, round of 16, quarter-finals, semi-finals and final. Every origin conserved stage probability mass. The subsequent non-overlapping windows contain **306 unique international matches**, scored using only earlier available results:

| Match forecast | Log loss |
| :--- | ---: |
| Joint country scale + fixed xG/ensemble | **0.94975** |
| Same fit without country offsets | 0.99690 |
| Joint country scale, goals only | **0.93960** |
| Joint Elo | 0.99016 |

Country offsets improve aggregate international loss, while **goals only beats the fixed xG blend** in this small replay. For fixtures where both clubs have xG, offsets also trail the no-offset comparison slightly (0.98010 vs 0.96370); the aggregate improvement comes from mixed/no-xG fixtures. The global weights remain frozen as specified. This is a transfer diagnostic, not evidence for universal xG benefit or a reason to retune on these two tournaments.

Mean position RPS after MD2/4/6 is **0.09170**; later league positions are already known. Across all 18 origins, stage Brier means are **0.08199 / 0.06974 / 0.04767 / 0.03891 / 0.02415** for reaching R16 / QF / SF / final / winning. These averages include stages already resolved at later origins; [per-origin metrics](docs/champions-league-evaluation-snapshots.json) retain the horizon and xG splits, alongside the [comparison report](docs/champions-league-evaluation.json). Global calibration used these domestic seasons, so the replay is retrospective rather than an independent weight-calibration holdout.

Verification also covered score-period extraction, strict origin/xG timing, legal draw slots, inherited home priority, a fixed first leg, completed shootout ties, neutral venues, normalized score distributions and numerical fit gradients. Existing package tests pass (**5 passed**); no new test files were added.

## Other existing priorities

Retain dated odds archives. Add dated disciplinary adjustments and deciding-playoff handling before claiming official-table equivalence. Keep conditional uncertainty and score-derived historical targets explicit. The global weights stay fixed unless explicitly recalibrated; UCL is the separate-package plan above, while larger model experiments remain outside the league package.
