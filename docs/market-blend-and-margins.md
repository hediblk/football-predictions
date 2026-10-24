# Market blend and margin removal, 24 October 2026

Two research-led experiments (R1 and R2). This is an offline comparison: no forecast, default, calibration artifact or site file changes.

- **R1: free log-linear pool.** Today's blend multiplies the component probabilities with weights constrained to sum to one. The fitted market weight sits at the cap (0.999999). Benter's second stage ([1994](https://ideas.repec.org/h/wsi/wschap/9789812819192_0019.html)) drops that constraint so a pool can sharpen the market or lean on another component.
- **R2: margin removal.** Every market probability here is de-margined proportionally, which ignores the favourite–longshot bias. The alternatives are additive, power, odds-ratio ([Cheung 2015](https://cran.uni-muenster.de/web/packages/implied/vignettes/introduction.html)) and Shin (1993).

**Result: both gain, but not for anything Floodlight publishes.** The daily refresh runs `football-predict --no-use-odds`. The Champions League uses archived quotes only inside its strength fit, with no direct fixture blending. So published match and season forecasts come from the no-odds pool, and that pool does not improve: freeing its weights or adding outcome intercepts changes held-out log loss by +0.00014 (SE 0.00011). The market-informed forecast does improve:

- Power or Shin margin removal: about −0.0003 to −0.0007 on the top five leagues, and −0.0017 on six outside leagues.
- A free pool: about −0.0006 to −0.0019.

The two mostly fix the same thing, a market whose proportional probabilities are not sharp enough.

The most useful finding is diagnostic. In every fold, the free pool puts a small **negative** weight on our model and more than full weight on the market. Where the market departs from our model, it is right more often than its own price says. The gap between the published model and the market is largest in July–September and April–June, and in fixtures with a promoted club.

## Data

- **Dataset:** the saved calibration dataset `out/global-calibration/features/dataset.csv` (sha256 `889897…a127`, matching artifact `global-4c0170be18f1`). It has 19,763 week-ahead fixtures in E0, SP1, D1, I1 and F1, 2015/16–2025/26, and 19,762 have pre-closing quotes (12,458 `Avg`, 7,304 `BbAv`). Model components are fixed at the production xG weight 0.75 and scale 1.3.
- **Raw prices:** re-read from the cached football-data.co.uk files with the dataset's own source priority and join keys (league, season, kickoff, normalized teams). The join is one-to-one. Proportional removal on the raw prices reproduces every dataset market probability within 1e-12, and the quote source matches on every row. Mean overround is 4.91% (median 4.80%). One Serie A 2025/26 average quote (Genoa) sums to 0.994, a negative margin. Every method keeps it, so the fixture set is identical to calibration. Additive removal never produced a negative probability.
- **Outside leagues:** the saved robustness dataset (P1, N1, B1, T1, G1, SC0; sha256 `40deb5…7627`, matching the artifact). These leagues were never used to fit weights, and their model is goals only.
- **Pinnacle:** pre-closing `PS` prices for 2015/16–2024/25 (17,991 fixtures). football-data.co.uk warns that its Pinnacle columns are unreliable from 23 July 2025, so 2025/26 is excluded.

## Protocol

These choices were fixed before any results were seen.

- **Scoring:** log loss with equal league-season weights, the calibration objective's weighting. Differences are paired on identical fixtures, with SEs clustered by league-season. 0.0005 is the roadmap's yardstick.
- **Primary design, expanding window:** fit on all seasons before *s* and score *s*, for s = 2017/18 to 2025/26 (9 seasons, 16,110 fixtures, 45 league-seasons). The protocol's held-out 2024/25–2025/26 (3,504 fixtures) is reported beside it.
- **Outside leagues:** pools fitted on the five leagues' earlier seasons with the goals-only component, scored on the six outside leagues the same way (15,208 fixtures, 54 league-seasons).
- **Today's blend** is refitted inside every fold with `fit.fit_weights`, the production procedure, on that fold's de-margined market. Free pools are `softmax(Σ θⱼ log pⱼ)`, fitted by convex weighted log loss. Optional draw and away intercepts are labelled where used.
- **Not reselected per fold:** the xG weight and scale. They were chosen on all eleven seasons, so the top-five comparisons are not independent of that choice. The outside leagues do not use xG.

## R2: margin removal, market only

Change in market log loss against proportional removal, ×1000 (SE). Negative is better.

| Method | Top five, expanding | Top five, held-out 2024–26 | Outside leagues, expanding |
| :--- | ---: | ---: | ---: |
| Proportional (today) | 0.96944 | 0.97100 | 0.94935 |
| Additive | −0.36 (0.19) | −0.76 (0.41) | |
| Power | −0.34 (0.20) | −0.73 (0.47) | **−1.71 (0.36)** |
| Odds ratio | −0.30 (0.13) | −0.54 (0.31) | |
| Shin | −0.34 (0.14) | −0.65 (0.31) | −1.32 (0.24) |

Every alternative improves on proportional removal in every test. The top-five gains are below the yardstick. The outside leagues gain more, consistent with their larger margins. On Pinnacle's lower-margin prices the methods barely differ: 0.96832 proportional, 0.96826 power and 0.96823 Shin, expanding 2017/18–2024/25. On the same fixtures, the average prices score 0.96863 with proportional removal but 0.96833 with power. **Most of Pinnacle's apparent edge over the average is margin removal.**

## R1: free pools with the market

Change against today's blend, which equals the proportional market at weight 0.999999, ×1000 (SE).

| Pool | Top five, expanding | Top five, held-out | Outside leagues |
| :--- | ---: | ---: | ---: |
| Market × scale (proportional prices) | −0.34 (0.24) | −0.69 (0.51) | −1.28 (0.32) |
| Market + scale + intercepts (proportional) | −0.47 (0.27) | −1.18 (0.59) | −1.70 (0.36) |
| Model + Elo + market, free (proportional) | **−0.68 (0.36)** | −1.59 (0.56) | −1.43 (0.35) |
| Power market, no fitting | −0.34 (0.20) | −0.73 (0.47) | −1.71 (0.36) |
| Model + Elo + market, free (power) | −0.61 (0.36) | **−1.66 (0.56)** | **−1.93 (0.46)** |
| Same, with intercepts (power) | −0.55 (0.35) | −1.77 (0.61) | −2.13 (0.50) |

Better league-seasons for the free pool on power prices: 28/45, 8/10 and 40/54. Intercepts do not help on the primary design.

**Coefficients:** the nine expanding folds, power prices.

- Our goal/xG model: −0.07 to −0.21.
- Elo: +0.01 to −0.14.
- Market: 1.12 to 1.26.
- On proportional prices the market coefficient is 1.19–1.34. A market scale alone is 1.06–1.11 on proportional prices and 1.00–1.04 on power prices. Power removal therefore gives a market that is about as sharp as it should be.

**What our model adds beyond the market** (free pool minus market scale, power prices), ×1000 (SE):

- Top five, expanding: −0.32 (0.26)
- Top five, held-out: −0.91 (0.38)
- Outside leagues: −0.21 (0.18)
- Pinnacle prices: about −0.2

The sign is negative in every test, because the coefficients are. Our model's own information is already in the price. The pool gains by moving *away* from our model and toward the market's departures from it.

## The published no-odds pool

Change against today's constrained main/Elo pool, ×1000 (SE).

| Pool | Top five, expanding | Top five, held-out | Outside leagues (goals only) |
| :--- | ---: | ---: | ---: |
| Free weights | +0.14 (0.11) | +0.01 (0.14) | −0.58 (0.26) |
| Free weights + intercepts | +0.15 (0.25) | −0.24 (0.50) | −0.87 (0.32) |

The free optimum on the top five (model 0.77–0.84, Elo 0.17–0.32) is today's ratio. The current calibration is already as sharp as this data supports. The goals-only gain in outside leagues does not apply to the published leagues, which use xG. It is a hint for clubs without xG, such as those in the Champions League, that would need its own test there.

## Where the market beats the published model

The no-odds blend at the artifact's weights against power-de-margined prices, all eleven seasons. Log-loss gap (SE). Descriptive only; no fitting.

| Group | Fixtures | Gap |
| :--- | ---: | ---: |
| Forecast in Jul–Sep | 3,675 | 0.0176 (0.0032) |
| Oct–Dec | 5,859 | 0.0135 (0.0016) |
| Jan–Mar | 6,025 | **0.0088 (0.0016)** |
| Apr–Jun | 4,203 | 0.0163 (0.0026) |
| A promoted club involved (2016/17 on) | 4,789 | 0.0159 (0.0025) |
| No promoted club (2016/17 on) | 13,147 | 0.0120 (0.0014) |

By league: E0 0.0096, SP1 0.0117, D1 0.0132, F1 0.0141, I1 0.0187. The early-season gap fits the parked promoted-team and preseason priors. The late-season gap nearly doubles the midseason one even though the model then has the most data. That fits end-of-season incentives, rotation and dead rubbers: information a price carries and a team-strength model does not.

## Decision

- **No production change.** `calibrated_weights.json`, the odds pipeline and published forecasts stay as they are. The published path does not use odds, and its pool is already at its free optimum.
- **If market blending is ever used**, adopt power removal plus a free three-coefficient pool, refitted by `football-calibrate`. This could be a `--use-odds` forecast, a backtest, or the Champions League fixture blend. Proportional prices with a fitted market scale reach most of the same gain, but power removal keeps working where margins differ.
- **Market yardstick (feature-plan Task 14):** compare the model with power-de-margined prices. Proportional removal understates the market by about 0.0003–0.0017 log loss.
- **Odds archive:** recording each fixture's mean bookmaker overround would make power removal exact for archived quotes, including the Champions League quotes in Plan E. With a typical margin assumed instead, power removal of the historical average prices agrees with the exact result within 0.000005 log loss when the assumed margin is the true mean, and costs about 0.0001 when it is two points off.
- **Next model work:** the late-season gap is the clearest target (R3: low-stakes fixtures, using the existing stakes calculation), then the early-season and promoted-club gap.

## Limitations

- Historical quote times are approximate. The protocol's origins are Tuesday or Friday 00:00 UTC, and the quotes were collected later that day. The market may therefore hold up to about a day of later news. That widens the gap and could produce part of the negative model weight. Live quotes must be observed before the origin.
- Live probabilities average per-book proportional removal across The Odds API's bookmakers; historical ones remove the margin from average decimal prices. Their margins and timing differ, so fitted market coefficients would need refitting on archived live quotes before use.
- The xG weight and scale were selected on all eleven seasons. The expanding window and held-out seasons are therefore not independent tests of the whole model. The outside leagues are.
- Two held-out seasons give limited evidence. The primary expanding gains are 1.7 to 1.9 SEs.

## Reproduce

From the repository root, with the saved datasets and the football-data.co.uk cache (`.cache/football-data-uk`):

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python -m forecast_calibration.market_blend --out-dir out/market-blend
```

It checks both dataset hashes against the artifact and verifies the raw-price join. It writes `results.json` (summaries, fold coefficients, gap breakdown and the code hash) and per-fixture losses for every method and design. The run takes about 40 seconds.
