# Eleven-season miss report

17 October 2026 · [Evaluation plan, Task 1](evaluation-plan-2026-10-17.md)

Keep the **0.5 xG margin**. Do not increase draw calls or show the before-first-goal toggle. Keep xG-scored log loss as a description of agreement with observed chances, alongside real log loss; it is unsuitable for choosing the production model. The historical forecasts have essentially no aggregate goal deficit against actual goals, although they increasingly undershoot Understat xG in recent seasons.

No model, calibration artifact, site code, published forecast or historical observation was changed.

## Data, reproduction and uncertainty

The exact saved calibration dataset contains **19,763 unique fixtures**, five leagues (E0: Premier League; SP1: La Liga; D1: Bundesliga; I1: Serie A; F1: Ligue 1), 2015/16–2025/26; 2014/15 is warm-up history. Its SHA-256 is `889897330dcf19f48977a06ba62895c4b599027a89b444a91aee747c51a7a127`. The saved artifact is `global-4c0170be18f1`: xG weight 0.75, scale 1.3, ridge 2, decay 0.003, main/Elo shares 0.8441680232595445/0.15583197674045546, no odds. Every forecast precedes kickoff. Training counts and last availability dates are checked against the saved features. Unknown historical kickoff times retain the dataset's noon anchor; results and xG retain its next-day availability approximation.

Saved features omit goal rates. Replaying their original Tuesday/Friday origins through the existing model and `describe_match` recovers the expected goals of the **blended scoreline distribution**, as used on the site. Maximum absolute discrepancy between replayed and saved DC/Elo probabilities is **1.11 × 10⁻¹⁶**. Forecast probabilities themselves come from the saved features. These are reconstructed forecasts, not archived publications. The fixed calibration used these seasons, so neither the whole sample nor the last two seasons is an independent calibration holdout here.

**Observed xG covers 19,759 fixtures (39,518 team-games).** The original join rejects Union Berlin–Bochum 2024/25, Sassuolo–Pescara 2016/17, Udinese–Roma 2023/24 and Caen–Toulouse 2017/18 because the score/date checks fail. All four remain in call/outcome counts, with unknown xG. No zero xG is imputed.

**Validated shot timings cover 19,756 fixtures.** Beyond those four, three match payloads lack complete goal-event coverage: Oviedo–Villarreal 2025/26, Holstein Kiel–Bochum 2024/25 and Bastia–Lyon 2016/17. Checks cover match/side/team/date/final-score identities, duplicate shot IDs, finite shot xG in [0,1], valid minutes and the total number of goal events, including own goals. A missing or invalid roster does not by itself invalidate otherwise complete shots. Own goals mark the stopping time but contribute no xG. No raw responses were rewritten.

Whole-game contract quantities use the **original league-listing xG vintage** attached to calibration inputs. The raw match payloads were fetched in October 2026 and sometimes differ. Game-state comparisons therefore report both the original-xG comparison and a comparison using the same raw-shot vintage on both sides. Whole-game verdicts differ between vintages in **1.40% ± 0.08 percentage points** of matched fixtures; mean absolute xG difference is **0.0221 ± 0.0006 per team-game**. This is kept separate from the pre-goal effect.

The frequency comparator uses each league's exact prior five seasons, frozen before the target season, through the existing `frequency_baseline`. Twelve previously missing 2010/11–2013/14 result CSVs for Germany, France and Italy were fetched into the provider cache to complete it. They only supply this baseline; they do not alter the saved forecasts or fitting history. All subsequent replay and shot analysis is offline and fails on a missing required cache. URLs and content hashes are recorded.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python -m forecast_calibration.miss_report \
  --dataset /Users/hedibelkahia/codes/football/out/global-calibration/features/dataset.csv \
  --cache-dir /Users/hedibelkahia/codes/football/.cache \
  --out-dir out/miss-report
```

Use the installed domestic and forecast-calibration packages. `--workers` controls replay processes; `--replay-only` stops before analysis. Unchanged input/code signatures reuse per-season replays. The analysis-only entry point is `python -m forecast_calibration.miss_analysis` with the same three path arguments.

All ordinary error bars below are **one clustered standard error**, not 95% intervals. For a mean, with residual sums S₍g₎ within G clusters, SE = √[G/(G−1) × ΣS₍g₎²] / n. Clusters are **league-season**: 55 pooled, 11 within a league, five within a season. Within one league-season, use **forecast origin** instead, keeping fixtures sharing a fitted model together. Each team-game goal measure is first averaged within its fixture. Counts are exact sample totals; their reported SE is n times the corresponding rate SE, interpreting uncertainty at fixed sample size. Actual-minus-expected counts and model contrasts use paired residuals, not independent errors. Empty estimates have no SE; an unobserved cell's empirical zero SE does not establish zero population risk.

Five-cluster season estimates are descriptive and fragile; do not read ±2 SE as a reliable 95% interval there. SEs condition on fixed calibration and source vintages, and do not include provider/model uncertainty or dependence across league-seasons. Ranking intervals and precision-ratio intervals use **2,000 paired league-season cluster bootstrap replicates, seed 7**, retaining all matches in a sampled cluster. All pooled means are match-weighted; the calibration artifact instead weights league-seasons equally. Real no-odds log loss on all 19,763 matches is **0.97979 ± 0.00438**. Equal-league-season weighting reproduces the artifact's **0.980561255293** loss; the scoring comparisons below use the common xG-covered subset.

[Complete contract tables](eleven-season-miss-report-tables.md) give every matrix cell, expected/actual count, miss-kind × verdict cell, goal level/error and score with SEs for all leagues, seasons and **all 55 league-season combinations**. They also contain pooled and early/recent cohorts. Detailed draw bins, threshold sensitivities, transitions and candidate scores at those same scopes are in `out/miss-report/estimates.csv`.

## Calls and misses

The pooled matrix has home/draw/away columns and call rows; SEs are in the complete tables.

| Called / actual | Home | Draw | Away |
| --- | ---: | ---: | ---: |
| Home | 6,975 | 3,186 | 2,640 |
| Draw | 13 | 14 | 16 |
| Away | 1,722 | 1,759 | 3,438 |

**10,427 of 19,763 calls are correct: 52.76% ± 0.43 pp.** There are 4,945 draw misses, 4,362 upsets and 29 missed draw calls. The draft's three miss kinds are not exhaustive: when a draw is called but a side wins, calling that an “upset” can falsely say the favourite lost. Add `missed_draw_call`. `called` takes precedence when the maximum-probability outcome happens. Calls break exact ties home, draw, away; the favourite breaks a home/away win-probability tie toward home.

| Outcome | Expected | Actual | Actual − expected ± SE |
| --- | ---: | ---: | ---: |
| Home | 8,639.9 | 8,710 | +70.1 ± 68.3 |
| Draw | 4,850.8 | 4,959 | +108.2 ± 57.6 |
| Away | 6,272.3 | 6,094 | −178.3 ± 66.2 |

The aggregate away overprediction is clearer than the draw shortfall. This report describes it without changing probabilities.

## 1. Draw calibration and extra draw calls

Draws are the most likely outcome in **43 fixtures, 0.218% ± 0.057 pp**; 14 of those calls are right. Rare draw calls coexist with roughly a quarter of matches ending level. The forecast is a probability distribution, not a promise that its largest component will occur.

Bins are left-closed/right-open. The final column is actual minus predicted, in percentage points, with its paired clustered SE.

| Draw probability bin | n | Predicted % ± SE | Actual % ± SE | Gap pp ± SE |
| --- | ---: | ---: | ---: | ---: |
| [0.0, 0.1) | 288 | 7.91 ± 0.12 | 9.38 ± 1.61 | 1.46 ± 1.61 |
| [0.1, 0.15) | 913 | 12.98 ± 0.05 | 12.71 ± 1.22 | -0.27 ± 1.22 |
| [0.15, 0.2) | 2,222 | 17.82 ± 0.03 | 17.96 ± 0.79 | 0.14 ± 0.80 |
| [0.2, 0.25) | 5,467 | 22.90 ± 0.02 | 24.07 ± 0.49 | 1.18 ± 0.48 |
| [0.25, 0.3) | 8,792 | 27.37 ± 0.04 | 28.40 ± 0.48 | 1.03 ± 0.48 |
| [0.3, 0.35) | 2,050 | 31.43 ± 0.05 | 29.17 ± 0.90 | -2.26 ± 0.89 |
| [0.35, 0.4) | 31 | 35.86 ± 0.13 | 19.35 ± 6.91 | -16.50 ± 6.84 |

| Win-probability gap | n | Predicted % ± SE | Actual % ± SE | Gap pp ± SE |
| --- | ---: | ---: | ---: | ---: |
| [0.0, 0.1) | 4,123 | 28.68 ± 0.18 | 29.91 ± 0.82 | 1.23 ± 0.77 |
| [0.1, 0.2) | 3,804 | 27.85 ± 0.17 | 28.10 ± 0.76 | 0.25 ± 0.76 |
| [0.2, 0.3) | 3,342 | 26.41 ± 0.17 | 27.35 ± 0.76 | 0.94 ± 0.78 |
| [0.3, 0.5) | 4,821 | 23.43 ± 0.15 | 24.08 ± 0.51 | 0.65 ± 0.50 |
| [0.5, 1.01) | 3,673 | 16.25 ± 0.16 | 15.85 ± 0.59 | -0.40 ± 0.57 |

Draw calibration is broadly close but not flat: the 20–30% bins modestly underpredict draws, while the ≥30% bins overpredict them. The 35–40% bin has only 31 matches and should not drive a rule. Closeness is **|p(home win) − p(away win)|**, using pre-match probabilities. Even near-balanced sides have a draw rate around 30%, so parity does not make draws the most likely outcome in general.

For a fixed sensitivity check, multiply p(draw) by k and renormalize the triple. The new call is its argmax. This is not a fitted recalibration. If only the displayed hard call changed, **log loss would be exactly unchanged**; the loss deltas below apply when the probabilities themselves are boosted.

| Draw multiplier k | Draw calls % ± SE | Accuracy change pp ± SE | Real log-loss change ± SE |
| --- | ---: | ---: | ---: |
| 0.75 | 0.000 ± 0.000 | 0.015 ± 0.017 | 0.00877 ± 0.00084 |
| 1 | 0.218 ± 0.057 | 0.000 ± 0.000 | -0.00000 ± 0.00000 |
| 1.1 | 1.326 ± 0.223 | -0.025 ± 0.066 | 0.00032 ± 0.00028 |
| 1.25 | 6.902 ± 0.651 | -0.557 ± 0.168 | 0.00349 ± 0.00065 |
| 1.5 | 24.602 ± 1.119 | -2.505 ± 0.269 | 0.01375 ± 0.00118 |
| 1.75 | 41.390 ± 1.139 | -4.807 ± 0.383 | 0.02800 ± 0.00163 |
| 2 | 53.661 ± 1.043 | -7.651 ± 0.424 | 0.04469 ± 0.00203 |

Calling more draws can help **particular retrospective cohorts**: k=1.1 gains six calls in 2015/16 (+0.329 ± 0.279 pp), and three over the latest two seasons (+0.086 ± 0.086 pp). Across all seasons it loses five calls (−0.025 ± 0.066 pp); k=1.25 loses 110. No tested positive boost supplies a convincing general gain in accuracy or log loss. A correct draw call is useful when supported by probabilities; a quota of draw calls is not supported. Keep argmax calls and report draw calibration by probability bin rather than judging it by draw-call frequency.

## 2. Goal level

Across xG-covered fixtures, predicted goals average **1.3879 ± 0.0137**, actual goals **1.3911 ± 0.0145**, and observed xG **1.4108 ± 0.0162** per team-game. The paired bias against actual goals is **−0.0031 ± 0.0068**: this is not a persistent historical scoring deficit like the current season's descriptive gap. Against xG it is **−0.0229 ± 0.0104**. MAE is **0.9052 ± 0.0069 against goals**, **0.6027 ± 0.0055 against xG**; the softer target is easier to track, which alone is not evidence of better result forecasts.

| League | Predicted ± SE | Goals ± SE | xG ± SE | Pred. − goals ± SE | Pred. − xG ± SE |
| --- | ---: | ---: | ---: | ---: | ---: |
| Bundesliga | 1.5221 ± 0.0306 | 1.5361 ± 0.0250 | 1.5258 ± 0.0369 | -0.0141 ± 0.0156 | -0.0038 ± 0.0249 |
| Premier League | 1.4103 ± 0.0236 | 1.4114 ± 0.0257 | 1.4394 ± 0.0389 | -0.0010 ± 0.0164 | -0.0290 ± 0.0199 |
| Ligue 1 | 1.3504 ± 0.0229 | 1.3545 ± 0.0207 | 1.3638 ± 0.0396 | -0.0041 ± 0.0102 | -0.0135 ± 0.0199 |
| Serie A | 1.3763 ± 0.0247 | 1.3638 ± 0.0323 | 1.3803 ± 0.0230 | 0.0125 ± 0.0201 | -0.0041 ± 0.0242 |
| La Liga | 1.3038 ± 0.0145 | 1.3150 ± 0.0207 | 1.3633 ± 0.0241 | -0.0112 ± 0.0130 | -0.0595 ± 0.0264 |

No league's all-season actual-goal bias exceeds one SE in magnitude. La Liga has the largest negative xG bias (−0.0595 ± 0.0264), though this is one of several league comparisons. The levels differ substantially between leagues; that is not itself a forecasting error.

| Season | Predicted ± SE | Goals ± SE | xG ± SE | Pred. − goals ± SE | Pred. − xG ± SE |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2015/16 | 1.3102 ± 0.0241 | 1.3346 ± 0.0267 | 1.3046 ± 0.0377 | -0.0244 ± 0.0167 | 0.0056 ± 0.0219 |
| 2016/17 | 1.3486 ± 0.0224 | 1.4173 ± 0.0320 | 1.3119 ± 0.0262 | -0.0686 ± 0.0181 | 0.0367 ± 0.0280 |
| 2017/18 | 1.3749 ± 0.0147 | 1.3553 ± 0.0099 | 1.3160 ± 0.0181 | 0.0195 ± 0.0185 | 0.0589 ± 0.0210 |
| 2018/19 | 1.3730 ± 0.0241 | 1.3743 ± 0.0511 | 1.4045 ± 0.0472 | -0.0013 ± 0.0278 | -0.0315 ± 0.0249 |
| 2019/20 | 1.3951 ± 0.0578 | 1.3959 ± 0.0691 | 1.4034 ± 0.0579 | -0.0008 ± 0.0263 | -0.0083 ± 0.0223 |
| 2020/21 | 1.4023 ± 0.0553 | 1.4003 ± 0.0516 | 1.3730 ± 0.0431 | 0.0019 ± 0.0122 | 0.0292 ± 0.0210 |
| 2021/22 | 1.4065 ± 0.0498 | 1.4053 ± 0.0464 | 1.4124 ± 0.0383 | 0.0012 ± 0.0193 | -0.0059 ± 0.0226 |
| 2022/23 | 1.4033 ± 0.0499 | 1.3831 ± 0.0548 | 1.4332 ± 0.0340 | 0.0202 ± 0.0224 | -0.0299 ± 0.0392 |
| 2023/24 | 1.4280 ± 0.0714 | 1.4423 ± 0.0751 | 1.5272 ± 0.0649 | -0.0143 ± 0.0273 | -0.0992 ± 0.0265 |
| 2024/25 | 1.4378 ± 0.0654 | 1.4138 ± 0.0546 | 1.5239 ± 0.0591 | 0.0240 ± 0.0222 | -0.0862 ± 0.0282 |
| 2025/26 | 1.3917 ± 0.0521 | 1.3824 ± 0.0624 | 1.5218 ± 0.0471 | 0.0092 ± 0.0216 | -0.1302 ± 0.0188 |

The actual-goal bias changes sign: the pooled deficit is −0.0686 ± 0.0181 in 2016/17, whereas 2024/25 and 2025/26 overpredict by +0.0240 ± 0.0222 and +0.0092 ± 0.0216. Individual league-seasons vary more: Bundesliga 2018/19 is −0.124 ± 0.049; Premier League 2024/25 is +0.095 ± 0.041. These are descriptive extremes among 55 cells, not corrected significance claims.

The recent xG gap is different: −0.0992, −0.0862 and −0.1302 per team-game over 2023/24–2025/26, despite near-zero actual-goal biases. Understat xG exceeds actual goals in those same cohorts. Do not label every deficit relative to xG “too few forecast goals,” or apply a goal uplift from this season's 301 matches. Show actual goals and xG as separate observed quantities, with their coverage.

## 3. The xG margin

The table uses the favourite's signed original observed-xG advantage. The boundary itself is level: |margin| ≤ threshold. Shares exclude the four missing-xG fixtures.

| Margin | Cohort | Won % ± SE | Level % ± SE | Lost % ± SE |
| --- | ---: | ---: | ---: | ---: |
| 0.3 | all | 59.85 ± 0.41 | 18.60 ± 0.37 | 21.55 ± 0.34 |
| 0.3 | draw | 49.64 ± 0.75 | 25.77 ± 0.62 | 24.60 ± 0.70 |
| 0.3 | upset | 24.84 ± 0.57 | 24.82 ± 0.73 | 50.34 ± 0.73 |
| 0.5 | all | 52.73 ± 0.42 | 30.66 ± 0.44 | 16.61 ± 0.35 |
| 0.5 | draw | 40.68 ± 0.61 | 40.92 ± 0.55 | 18.41 ± 0.60 |
| 0.5 | upset | 19.01 ± 0.63 | 39.86 ± 0.89 | 41.12 ± 0.76 |
| 0.7 | all | 45.62 ± 0.47 | 41.75 ± 0.53 | 12.63 ± 0.30 |
| 0.7 | draw | 31.86 ± 0.62 | 55.24 ± 0.61 | 12.90 ± 0.46 |
| 0.7 | upset | 13.90 ± 0.55 | 52.59 ± 0.86 | 33.51 ± 0.71 |

At 0.5, draw misses are **40.68% ± 0.61 pp won**, **40.92% ± 0.55 pp level**, **18.41% ± 0.60 pp lost** on chances. Upsets are **19.01% ± 0.63 pp won**, **39.86% ± 0.89 pp level**, **41.12% ± 0.76 pp lost**. Successful calls are 72.60% ± 0.45 pp won on chances. These are thresholded verdicts; they should not be compared directly to the current-season plan's “any positive xG lead” figures.

| Change | Fixtures relabelled level % ± SE |
| --- | ---: |
| 0.3 → 0.5 | 12.06 ± 0.29 |
| 0.5 → 0.7 | 11.09 ± 0.24 |

**Retain 0.5.** At 0.3, small leads become decisive labels; at 0.7, more than half of upsets become level. Half a goal is an understandable middle tolerance, retaining substantial won/lost groups without attaching a winner label to a slight chance edge. There is no external truth label here that identifies an optimal threshold; this is a display convention, not a tuned parameter or proof that a side deserved to win. Keep 0.3/0.7 as sensitivity outputs, not selectable site verdicts.

## 4. Before the first goal

For the draft definition, take shots with integer elapsed minute **strictly smaller than the first goal event's minute**. That excludes the scoring shot and every shot in that minute, since seconds/order within a minute cannot be established. Include own goals as stopping events; exclude their xG. A goalless game uses every shot. A first goal at elapsed minute <10 forces the draft verdict to `level`. The appendix retains this exact draft convention so its proposed contract can be audited.

The original whole-game xG verdict and draft pre-goal verdict disagree in **54.92% ± 0.39 pp** of the 19,756 paired games. With the raw-shot vintage used for **both** whole-game and pre-goal xG, disagreement is **55.09% ± 0.40 pp**. The large change is not a source-vintage artifact.

Same-source transition shares, as percentages of **all paired fixtures** (not row-conditional):

| Whole game / before goal | Won % ± SE | Level % ± SE | Lost % ± SE |
| --- | ---: | ---: | ---: |
| won | 13.76 ± 0.26 | 38.45 ± 0.36 | 0.61 ± 0.06 |
| level | 1.60 ± 0.09 | 27.37 ± 0.42 | 1.33 ± 0.08 |
| lost | 0.35 ± 0.04 | 12.75 ± 0.26 | 3.77 ± 0.16 |

| Same-source diagnostic | Share % ± SE |
| --- | ---: |
| Whole-game level | 30.31 ± 0.43 |
| Pre-goal level | 78.57 ± 0.34 |
| Won/lost → level | 51.19 ± 0.40 |
| Level → won/lost | 2.94 ± 0.13 |
| Direct won ↔ lost | 0.96 ± 0.08 |

The disagreement overwhelmingly reflects **loss of information**: most moves take a decisive whole-game verdict to level; direct won↔lost reversals are rare. Even excluding early goals, disagreement remains **50.43% ± 0.43 pp**. All **1,325 goalless games** agree under the same shot source, as required. The early rule alone affects **4,042 matches, 20.46% ± 0.36 pp**.

**Do not show the pre-goal toggle or export `xg_pre` for the site.** Its stopping time depends on scoring, and its usually short exposure makes the same absolute 0.5 margin much harder to clear. It cannot establish what would have happened without a goal or remove tactical game-state effects causally. Calling an early interval “level” also confuses insufficient evidence with evenly matched chances. If this lens is revisited, early intervals should be `unknown`/insufficient play, with exposure shown and a separately justified comparison. Keep the raw offline comparison available; it does not justify another site verdict now.

## 5. xG-scored log loss and model selection

The target q is the H/D/A distribution of **two independent Poissons whose means are the observed league-total xG**. Cross entropy is −Σqᵢ log pᵢ. The calculation includes the degenerate 0–0 means correctly and checks Poisson tail mass; it does not use the site's existing shot-Bernoulli retrospective outcome probabilities. It is a different target from actual-result log loss, not an unbiased, variance-reduced estimator of that loss.

Eleven fixed candidates are compared on exactly **19,759 fixtures**: the saved model, Elo, the prior-five-season frequency baseline, and eight DC/xG alternatives blended with the **same saved main/Elo ratio**. Elo and frequency remain standalone comparators. In the labels below, w is xG weight and s is strength scale; w=0 is goals only. No candidate weights are fitted, selected for production or written to the artifact.

| Candidate | Real loss ± SE | xG-scored loss ± SE | Real rank | xG rank |
| --- | ---: | ---: | ---: | ---: |
| model | 0.97974 ± 0.00439 | 1.02253 ± 0.00230 | 1 | 6 |
| w1s1.3 | 0.98026 ± 0.00448 | 1.02392 ± 0.00229 | 2 | 7 |
| w0.75s1.5 | 0.98036 ± 0.00462 | 1.02848 ± 0.00233 | 3 | 9 |
| w0.5s1.3 | 0.98047 ± 0.00432 | 1.02240 ± 0.00232 | 4 | 5 |
| w0.75s1 | 0.98261 ± 0.00401 | 1.01767 ± 0.00223 | 5 | 2 |
| w0.5s1 | 0.98261 ± 0.00408 | 1.01939 ± 0.00227 | 6 | 3 |
| w1s1 | 0.98361 ± 0.00396 | 1.01698 ± 0.00220 | 7 | 1 |
| w0.25s1 | 0.98362 ± 0.00415 | 1.02213 ± 0.00233 | 8 | 4 |
| w0s1 | 0.98563 ± 0.00424 | 1.02590 ± 0.00241 | 9 | 8 |
| elo | 0.99665 ± 0.00391 | 1.02916 ± 0.00238 | 10 | 10 |
| frequency | 1.07095 ± 0.00203 | 1.06483 ± 0.00131 | 11 | 11 |

Ranking agrees poorly: Spearman **0.282**, paired cluster-bootstrap 95% interval **[0.182, 0.409]**; Kendall **0.200**. The early-period Spearman is also 0.282; the latest-two-season value is **0.191 [0.118, 0.355]**, with only ten clusters. Agreement on weak baselines hides disagreement between the closely related models.

The clearest reversal is full unscaled xG, w=1/s=1. Against the saved model it **worsens real loss by 0.00387 ± 0.00055**, but **improves xG-scored loss by 0.00555 ± 0.00037**. Removing the scale at w=0.75 also worsens real loss (+0.00286 ± 0.00048) while improving the soft score (−0.00486 ± 0.00028). This diagnostic strongly rewards reproducing Understat's chances, including the compression the existing scale was designed to address.

There is less sampling variation, measured on **paired candidate-minus-production contrasts**, not just the level of each score:

| Candidate minus model | Real SE | xG SE | SE ratio [bootstrap 95% interval] | Variance reduction |
| --- | ---: | ---: | ---: | ---: |
| elo | 0.001144 | 0.000693 | 0.605 [0.465, 0.808] | 63.3% |
| frequency | 0.003628 | 0.002006 | 0.553 [0.451, 0.682] | 69.4% |
| w0s1 | 0.000711 | 0.000494 | 0.695 [0.507, 0.945] | 51.7% |
| w0.25s1 | 0.000583 | 0.000327 | 0.562 [0.427, 0.743] | 68.4% |
| w0.5s1 | 0.000496 | 0.000245 | 0.495 [0.399, 0.617] | 75.5% |
| w0.75s1 | 0.000480 | 0.000276 | 0.575 [0.449, 0.739] | 66.9% |
| w1s1 | 0.000552 | 0.000367 | 0.665 [0.520, 0.860] | 55.8% |
| w0.5s1.3 | 0.000247 | 0.000153 | 0.620 [0.461, 0.829] | 61.6% |
| w1s1.3 | 0.000264 | 0.000150 | 0.569 [0.437, 0.740] | 67.7% |
| w0.75s1.5 | 0.000328 | 0.000225 | 0.688 [0.554, 0.870] | 52.6% |

Across these ten contrasts, clustered SE ratios range **0.495–0.695**: about **31–51% smaller SEs**, or **52–76% less estimated sampling variance**. For the absolute model score on xG coverage, SE falls from 0.00439 to 0.00230 (48% smaller). These are precision gains **for a changed estimand**, not noise removed from actual results while preserving the same signal. The narrower errors can make the wrong selection more convincing. Keep real log loss primary; label xG-scored loss as an observed-chances diagnostic and show it beside real loss on the same coverage.

## Outputs and checks

`out/miss-report/` contains:

- `matches.csv.gz`: one row per forecast, input identities, goal expectations, probabilities, observed xG, shot/pre-goal totals, verdicts and all candidate losses.
- `contract.json`: every draft-contract quantity, plus the missing draw-call category, at all report scopes. Pre-goal fields here are research outputs only.
- `estimates.csv`: estimates, clustered SEs, denominators, cluster counts/units for contract fields and all diagnostics.
- `coverage.csv`, `shot_exclusions.csv`: every league-season's coverage and explicit shot exclusions.
- `rankings.json`, `noise.csv`: rank agreement, paired score contrasts, SE ratios and bootstrap intervals.
- `replay/`, `manifest.json`: resumable inputs, data/model/code hashes, per-match raw-response hashes, runtime versions, seed and output hashes.
- `contract-tables.md`: the generated source of the committed [complete tables](eleven-season-miss-report-tables.md).

The full existing offline pytest suite passed: **124 tests**, with 51 existing deprecation warnings. Replay checks reproduce saved probabilities, enforce forecast/training timing and result identities, and reconcile contract counts. Review also checks probability normalization, complete contract scope coverage, source/output hashes, and `git diff --check`. Outputs stay ignored under `out/`; the report, complete tables and small analysis modules are reviewable in the PR. No numerical baselines or production defaults were updated.
