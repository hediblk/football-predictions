# Non-penalty xG with a team penalty rate, 16 October 2026

Task B of the [model plan (16 October 2026)](model-plan-2026-10-16.md). This is an offline comparison. No forecast, default, calibration artifact or site file changes.

**Result: no clear win.** Both variants improve slightly on today's xG in held-out no-odds match log loss, but neither gain clears its noise. The penalty-rate variant only reaches the 0.0005 yardstick as a point estimate.

| Held-out 2024/25–2025/26, 3,504 matches | Log loss | Change vs xG ×1000 (SE) | Brier change ×1000 (SE) | RPS change ×1000 (SE) |
| :--- | ---: | ---: | ---: | ---: |
| Goals only (reference) | 0.99249 | +8.41 (1.56) | +5.63 (1.06) | +2.63 (0.50) |
| 1. xG (today's model) | **0.98412** | — | — | — |
| 2. npxG | 0.98364 | −0.48 (0.52) | −0.19 (0.36) | −0.09 (0.17) |
| 3. npxG + team penalty rate | 0.98351 | −0.61 (0.39) | −0.31 (0.27) | −0.15 (0.12) |

Negative is better. The penalty rate adds −0.13 (0.19) over npxG alone. The rate itself barely predicts penalties: its correlation with a team-game's actual penalty xG is 0.07. In an expanding-window check over nine seasons, both variants again come out below the yardstick. Title and top-four replays show no measurable difference. With the Elo-K change parked at 0.0005, this belongs beside it. The variant is cheap if `calibrated_weights.json` is rebuilt for another reason, but it does not justify a calibration PR by itself.

## Data and joins

- **Source:** the cached Understat `getLeagueData` responses for E0, SP1, D1, I1 and F1, 2014/15–2025/26. `teams[*].history` has one row per team-match with `xG`, `xGA`, `npxG` and `npxGA`.
- **Join:** `fetch_understat_matches(..., npxg=True)` joins history rows to `dates` by team title, venue (`h_a`) and the kickoff string. The default output (`npxg=False`) is unchanged. `attach_xg` carries `home_npxg`/`away_npxg` only when the source has them. The calibration loader passes the flag through, so npxG passes the same team-pair, two-day kickoff and final-score checks as xG.
- **Checks, all 60 league-seasons:** 21,589 results and 43,178 history rows, with 0 duplicate keys, 0 missing sides and 0 unused history rows. Every join is one-to-one. History `xG` matches `dates` xG within 1e-6 for every side (0 mismatches). Each side's `npxGA` equals the opponent's `npxG` (0 mismatches), and no penalty xG is negative. npxG attaches wherever xG does: 21,585 matches. The same four score or date mismatches as before are rejected (D1 2024/25, I1 2016/17 and 2023/24, F1 2017/18). Per-season counts: `out/npxg-penalty-rate/join_checks.csv`.
- **Penalty xG** = xG − npxG per team-match. It averages 0.120 per team-game: from about 0.10 in the Premier League to 0.13 in Serie A and Ligue 1. 14.7% of team-games have any, and the median nonzero value is 0.76, one penalty.
- **Timing:** unchanged from the protocol. npxG comes from the same response as xG and is treated as available the next UTC day after the local match date. Historical publication times are not reconstructed.

## Variants

All three use the calibration protocol's Dixon–Coles, Elo and `fit_xg_strengths` (decay 0.003, ridge 2, up to two prior seasons), refitted at each origin. They then use `blend_xg_strengths` and the log-linear main/Elo pool.

1. **xG:** today's model. Its probabilities reproduce the saved calibration dataset (`out/global-calibration/features/dataset.csv`) to within 1e-16. Its held-out loss, 0.98412, equals the artifact's chronological check.
2. **npxG:** `fit_xg_strengths` on non-penalty xG for and against. Nothing else changes.
3. **npxG + team penalty rate:** npxG strengths plus each team's penalty xG for and against:
   - Each team-game's penalty xG is divided by the league's time-decayed mean for that venue (home or away). The result is averaged with the strength fit's decay weights over the same training rows. It is shrunk toward 1, the league mean, by *k* pseudo-games: `rate = (Σ w·obs + k) / (Σ w + k)`.
   - The expected penalty xG for home side *i* against away side *j* is `home mean × for_i × against_j`, and likewise for the away side.
   - It is added to the npxG rate, `exp(intercept + home + attack_i + defence_j)`. The log of the total, relative to an average pairing's total, replaces `attack_i + defence_j` in the blend. It therefore gets the same xG weight and scale. Teams without xG strengths get no penalty term.
   - *k* is chosen from {5, 10, 20, 40, 80, 160, ∞} with the xG weight and scale; ∞ gives every team the league mean.

The rate's form, venue normalisation, *k* grid, clustering and the extra expanding-window check were all fixed before any results were seen.

## Protocol

The same leagues, seasons 2015/16–2025/26 (19,763 matches) and Tuesday/Friday 00:00 UTC origins as `football-calibrate`. For each variant, the xG weight (0, 0.25, 0.5, 0.75, 1), xG scale (1–1.5), main/Elo/market weights and, for variant 3, *k* are selected with `select_weights` on 2015/16–2023/24 only. They are then frozen for 2024/25–2025/26. The selection objective is the protocol's: half no-odds log loss and half with-odds log loss. With odds, probabilities follow the market, so in practice the selection is on no-odds loss. All results here are no-odds, with equal league-season weights.

Standard errors are paired differences against xG, clustered by league × forecast origin (403 clusters in the holdout), so matches forecast from the same fit share a cluster.

| Selected on 2015/16–2023/24 | xG weight | xG scale | *k* | Main share without odds | Training no-odds log loss |
| :--- | ---: | ---: | ---: | ---: | ---: |
| xG | 0.75 | 1.3 | — | 82.65% | 0.97978 |
| npxG | 0.75 | 1.3 | — | 82.64% | 0.97946 |
| npxG + penalty rate | 0.75 | 1.4 | 80 | 82.79% | 0.97945 |

On the training seasons, *k* = 40–160 are nearly tied (0.97945–0.97948). Weak shrinkage is worse: *k* = 5 gives 0.97982, worse than plain xG. Selection picks 80, so a team's own decayed record and the league mean get similar weight.

## Held-out results by league and season

Log loss change vs xG, ×1000 (clustered SE); negative is better.

| League-season | Matches | xG log loss | npxG | npxG + penalty rate |
| :--- | ---: | ---: | ---: | ---: |
| Bundesliga 2024/25 | 306 | 1.0071 | +0.04 (1.39) | +0.17 (1.00) |
| Bundesliga 2025/26 | 306 | 0.9681 | +1.29 (1.60) | +0.65 (1.09) |
| Premier League 2024/25 | 380 | 0.9714 | −0.78 (1.20) | −0.99 (0.83) |
| Premier League 2025/26 | 380 | 1.0226 | −0.04 (1.11) | +0.02 (0.83) |
| Ligue 1 2024/25 | 306 | 0.9777 | −1.36 (2.65) | −1.30 (2.06) |
| Ligue 1 2025/26 | 306 | 0.9914 | −1.80 (1.44) | −1.40 (1.19) |
| Serie A 2024/25 | 380 | 0.9682 | −0.24 (1.95) | −0.48 (1.52) |
| Serie A 2025/26 | 380 | 0.9943 | −1.32 (1.80) | −0.93 (1.41) |
| La Liga 2024/25 | 380 | 0.9633 | −0.56 (1.49) | −1.09 (1.04) |
| La Liga 2025/26 | 380 | 0.9771 | −0.06 (1.43) | −0.73 (0.97) |
| **2024/25** | 1,752 | 0.9775 | −0.58 (0.80) | −0.74 (0.61) |
| **2025/26** | 1,752 | 0.9907 | −0.38 (0.67) | −0.48 (0.50) |
| **All** | 3,504 | **0.9841** | **−0.48 (0.52)** | **−0.61 (0.39)** |

Seven of ten league-seasons improve under variant 3. The Bundesliga is worse in both seasons and the Premier League is flat in 2025/26; Ligue 1 gains most. Brier and RPS follow the same pattern; every league-season is in `out/npxg-penalty-rate/holdout_metrics.csv`.

**Expanding window (robustness, not the holdout):** for each season from 2017/18 to 2025/26, every setting is reselected on all earlier seasons and scored on that season. Over 16,111 matches, npxG gives −0.36 (0.27) and the penalty rate −0.47 (0.24). npxG is worse in three of nine seasons and the penalty rate in two. Serie A is flat (+0.12), and Ligue 1 gains most (−1.19, SE 0.55). Selected *k* ranges from 40 to ∞ and is 80 in each of the last four seasons. See `expanding_metrics.csv` and `expanding_selection.csv`.

## The penalty rate on its own

Mean squared error of each team-game's expected penalty xG, ×1000 (`penalty_rate_check.csv`):

| *k* | 5 | 10 | 20 | 40 | 80 | 160 | ∞ (league mean by venue) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Training seasons | 91.89 | 91.13 | 90.46 | 90.04 | **89.92** | 89.97 | 90.21 |
| Held-out seasons | 88.92 | 88.20 | 87.52 | 87.05 | 86.83 | **86.79** | 86.88 |

The team rate beats the league mean by only 0.3% of the error. At *k* = 80, the expected penalty xG has a standard deviation of 0.034 across team-games, against 0.027 from venue alone. Penalties are close to a league-wide constant once they are measured this way. Most of the gain in variant 3 therefore comes from removing penalties from the strength fit (variant 2), not from the rate.

## Season replays (checks)

Each variant's frozen holdout settings were replayed on all five leagues, 2016/17–2025/26, after rounds 5, 10, 20 and 30. That gives the same 199 snapshots as [Plan C](../PLAN.md). Each replay used 10,000 simulations with seed 7 and no odds; tables are rebuilt from match scores. Eight of these ten seasons were in the selection set, so only the held-out rows are out of sample. SEs come from league-season means: 50 league-seasons overall and 10 held out. Brier scores are averaged over clubs.

| Metric | xG | npxG − xG (SE) | Penalty rate − xG (SE) | Held out: npxG − xG | Held out: penalty rate − xG |
| :--- | ---: | ---: | ---: | ---: | ---: |
| Title log loss | 0.5916 | +0.0087 (0.0105) | +0.0061 (0.0079) | −0.0135 (0.0137) | −0.0107 (0.0108) |
| Top-four log loss | 0.1623 | +0.0004 (0.0012) | +0.0001 (0.0009) | −0.0004 (0.0015) | +0.0002 (0.0014) |
| Title Brier | 0.01642 | −0.00005 (0.00024) | +0.00000 (0.00018) | −0.00074 (0.00042) | −0.00050 (0.00032) |
| Top-four Brier | 0.05013 | +0.00029 (0.00040) | +0.00011 (0.00029) | +0.00005 (0.00069) | +0.00012 (0.00056) |
| Position RPS | 0.06823 | −0.00025 (0.00025) | −0.00026 (0.00018) | −0.00008 (0.00062) | −0.00018 (0.00045) |
| Expected-points MAE | 5.057 | −0.029 (0.013) | −0.026 (0.010) | −0.009 (0.031) | −0.019 (0.021) |

Title and top-four log loss move by less than their standard errors, in opposite directions over all seasons and in the held-out seasons. Expected-points error improves by about 0.03 points, but mostly in seasons that took part in selection.

## Limits

- The holdout is two seasons. Its SE (0.0004–0.0005) is about the size of the yardstick, so it cannot confirm a gain of that size. The expanding window adds seasons but reuses them for selection.
- Understat's penalty xG is a fixed value per penalty (median 0.76), so the rate measures how often penalties are won, not how well they are taken. Penalty goals still enter the Dixon–Coles goal fit in every variant.
- The penalty term's form (multiplicative for and against, venue means, one shrinkage for both directions) is one reasonable choice; the alternatives were not searched.

## Reproduce

From the repository root, with the shared `.cache` (features and replays each take several minutes on 7 workers):

```bash
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m forecast_calibration.npxg all --workers 7
```

This writes `out/npxg-penalty-rate/`: the feature files (`features/*.parquet`, one per league-season), `join_checks.csv`, `selection.json`, `holdout_metrics.csv`, `expanding_*.csv`, `penalty_rate_check.csv` and `replay_*.csv`. Code: [`npxg.py`](../packages/forecast-calibration/src/forecast_calibration/npxg.py); the join is in [`xg.py`](../src/standing_prediction/xg.py).
