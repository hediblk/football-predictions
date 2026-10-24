# Late-season stakes, 24 October 2026

R3 in the [research backlog](research-backlog-2026-10-24.md). This is an offline comparison: no forecast, default, calibration artifact or site file changes.

**Question.** The published no-odds model trails the market by 0.0163 log loss in April–June but only 0.0088 in January–March, even though the model has the most data late in the season (R1, in the backlog). Do fixtures where a side has nothing left to play for explain that gap? If so, does a stakes term improve the published forecast?

**Result: the gap is real but a stakes term does not close it.**

- After half the season, fixtures where exactly one side has nothing at stake trail the market by 0.0171. Fixtures where both play for something trail by 0.0091.
- Adding a stakes shift to the published blend changes held-out log loss by −0.00010 (SE 0.00031) over all fixtures. On the flagged fixtures alone it is −0.00073 (SE 0.00139). Neither is distinguishable from zero, and both are below the 0.0005 yardstick.
- The fitted effect is consistent: in all nine folds, the side with something to play for gains about 0.1 in logit, and a dead rubber between two sides with nothing has fewer draws. But the effect is small.
- The market already prices it: the same term added to the market makes it worse (+0.00018, SE 0.00014). Whatever the market knows about these games is mostly something other than our stakes measure.

## Data and stakes

- **Dataset:** the saved calibration dataset (19,763 fixtures, E0/SP1/D1/I1/F1, 2015/16–2025/26; hash checked against artifact `global-4c0170be18f1`).
- **Simulation at each origin:** at every Tuesday or Friday 00:00 UTC origin with at least half the season's results available, the production no-odds season simulation is rerun as it would have been then:
  - Refit Dixon–Coles, xG (weight 0.75, scale 1.3) and Elo on the results available at the origin, with decay 0.003, ridge 2 and two prior seasons.
  - Build the remaining fixtures with `build_fixture_specs` and the artifact's weights, rebuild the table from results available then, and run `simulate_season_scores` (4,000 simulations, seed 7), tracking that origin's fixtures.
  - For every tracked fixture, the refitted goal/xG and Elo probabilities match the saved dataset within 1e-9, so the stakes come from the same forecasts that are scored. The build stops on any mismatch.
- **Stake of a side:** the largest change in its title, top-4, top-6 or relegation-zone (bottom three) chance between two of its results. A result needs at least 50 simulations behind it to count. A side has **nothing to play for** in a fixture when its stake is below 3 points. 1 and 10 points are sensitivities; all three thresholds were fixed before results.
- **Coverage:** 9,694 fixtures (49%) have stakes; the first-half fixtures have none and get no adjustment.
- **Not modelled:** points deductions, playoffs and European places won through cups are not in the simulated tables. Ligue 1 2019/20 ended early, and its later origins simulate only the fixtures actually played; that is knowledge of a schedule change not available at the time.
- **Sanity check:** on the 2023/24 Premier League's final day, Manchester City's title swing is 77 points and Arsenal's 14. Liverpool, already third, have nothing at stake.

## Protocol

- **Base forecast:** the published blend, `0.844·log p(goal/xG) + 0.156·log p(Elo)` at the artifact's weights.
- **Stakes term:** two coefficients are added to the logits.
  - *Asymmetry:* +1 when only the away side has nothing to play for, −1 when only the home side has nothing. It moves home-win against away-win.
  - *Both have nothing:* a draw shift.
- **Fitting:** expanding window. The coefficients are fitted on all seasons before *s* and scored on *s*, for s = 2017/18–2025/26: 16,111 fixtures, 45 league-seasons.
- **Scoring:** log loss with equal league-season weights, paired SEs clustered by league-season.
- **Market check:** the same term is fitted on the proportional-de-margined market instead of the model.

## Results

Change in held-out log loss ×1000 (SE), negative is better. League-seasons better in brackets. Outside flagged fixtures the term is zero, so the counts are the same for every scope.

| Threshold (nothing to play for) | Flagged share | All fixtures | Flagged fixtures | Forecast in Apr–Jun | Same term on the market |
| :--- | ---: | ---: | ---: | ---: | ---: |
| **3 points (primary)** | 24.6% | −0.10 (0.31) [26/45] | −0.73 (1.39) | −0.26 (1.21) | +0.18 (0.14) |
| 1 point | 18.0% | −0.26 (0.39) [25/45] | −2.29 (2.16) | −1.59 (1.44) | +0.13 (0.16) |
| 10 points | 36.0% | −0.32 (0.29) [27/45] | −0.80 (0.84) | −1.32 (1.02) | +0.02 (0.12) |

**Coefficients**, nine folds, primary threshold:

- Asymmetry: +0.09 to +0.18 for the model, against +0.01 to +0.09 for the market.
- Both have nothing: draws −0.04 to −0.19 for the model, against −0.04 to −0.18 for the market.

The model's asymmetry is larger, so the market already leans the same way.

**Gap to the market by stakes group** (model minus market, test seasons, primary threshold):

| Group | Fixtures | Gap |
| :--- | ---: | ---: |
| First half, no stakes computed | 8,195 | 0.0134 (0.0015) |
| Both play for something | 3,953 | 0.0091 (0.0017) |
| One side has nothing | 2,900 | **0.0171 (0.0032)** |
| Neither has anything | 1,062 | 0.0055 (0.0046) |

These groups also differ in other ways. For example, the one-sided fixtures are often a motivated favourite against a mid-table side. The table describes where the gap sits; it does not show that motivation causes it.

## Decision

- **Not adopted.** The best variant gains less than the yardstick within noise. A production version would need two simulation passes, first for stakes and then for adjusted probabilities.
- **What remains open:** title and relegation Brier scores could still move, since the term shifts the motivated side's results. But title outcomes are too few to separate models (see the roadmap), and the match-level evidence does not justify the extra pass.
- **The one-sided gap (0.0171) is the target.** Information the market has there, and our team strengths lack, is more likely rotation and team news than motivation alone. Confirmed lineups were tested earlier ([Task 8](expected-xi-forecast-adjustment.md)) without a gain over all fixtures; a lineup check restricted to these late-season fixtures would be the narrow follow-up.

## Limitations

- Historical quote times are approximate (later on the origin day), so the market may hold some later news.
- The flag is broad. At 3 points, a quarter of the tested fixtures (about half of second-half fixtures) have one side flagged, because one match rarely moves a mid-table side's chances. The 1-point threshold is closer to a true dead rubber.
- The xG weight and scale were chosen on all eleven seasons, so the base forecast is not fully independent of the test seasons. The stakes coefficients themselves are always fitted on earlier seasons.

## Code

The experiment code is not on `main`, because the result was not adopted. It is kept on branch `codex/late-season-stakes-code` (commit `1f49c57`) as `packages/forecast-calibration/src/forecast_calibration/late_stakes.py`. From the repository root on that branch, with the saved dataset and provider caches:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python -m forecast_calibration.late_stakes --workers 6 --out-dir out/late-stakes
```

- **Outputs:** per league-season stakes in `out/late-stakes/parts/` (reused when present), plus `stakes.csv` and `results.json` (code hash `1c09d221b80c…`).
- **Runtime:** about seven minutes with six workers.
- **Reuse:** the stakes build (`build_part`) is the reusable piece if lineup or rotation checks on late one-sided fixtures are tried later.
