# Expected-XI: EA-prior follow-up, 17 October 2026

Task 7b merged in [PR #61](https://github.com/hediblk/football-predictions/pull/61). This is the requested follow-up to [Task 8's original flat-prior evaluation](expected-xi-forecast-adjustment.md), updating [PR #60](https://github.com/hediblk/football-predictions/pull/60). Production forecasts, calibration settings and site data remain unchanged.

**Result: the EA prior does not pass the forecast gate.** Earlier seasons again select recent start share, with **w = 1** for EA and **w = 2** for the aligned flat control. On the same 3,500 held-out fixtures, baseline log loss is **0.983295**, flat is **0.984153**, and EA is **0.983740**. EA's gain over baseline is **−0.000446 (clustered SE 0.000703)**. Brier and RPS also worsen. EA is less harmful than the selected flat adjustment by **0.000412 (SE 0.000587)**, but that is not a gain over the unchanged model. Keep zero forecast weight.

In 2024/25 EA is effectively equal to baseline (gain +0.00000021, SE 0.001040); in 2025/26 it is worse by 0.000892 (SE 0.000949). The confirmed-starters oracle gains only **0.000031 (SE 0.001357)**. Neither expected nor confirmed lineups establish a deployable gain with this offset.

## Matched protocol and prior adapter

The origins, league/season coverage, available-result and xG cutoffs, XI probability rules, usual-start shares, goal-rate formula, fixed global blend, score support, weight grid, earlier-only selection, odds approximation and league/origin-clustered errors are those in the [original protocol](expected-xi-forecast-adjustment.md#protocol). Both priors use 19,749 fixtures and 2,257 league-origins, with 14 common exclusions; 19,748 have odds. Both have 39,392 scorable team-games and 106 no-history sides retained with zero offsets. The expected-XI probabilities and all baseline rates/Elo probabilities match exactly between priors and with the original run. No newly rated player causes a fixture exclusion.

The adapter uses Task 7b's `EaPrior.fit` and the merged `Fold.beta` interface. Every training row uses ratings available before **its own season**. Prior slopes and player deviations fit only earlier seasons. Ridge is selected from earlier folds and frozen before 2024/25; each season's selected ridge is refitted **after** the candidate loop, so a candidate's temporary slope cannot become the saved effect. Weights and XI method are independently chosen per prior using 2017/18–2023/24, then frozen for the last two seasons.

Task 7b centres ratings over the supplied player pool. Using evaluation-season appearances to define that pool would let future sheets change prior means. Here the EA pool contains the fixed matched identity catalogue plus players observed in earlier seasons; only eligible rating vintages give catalogue members values. The flat control uses all earlier appearances too, including 2014 warm-up players: their usual-start shares can still occur in 2015 training rows. This gives both priors the same nonzero training columns. Additional EA columns have zero training entries and retain their prior-only effects. Unlinked/unrated players get zero prior. Missing IDs are never re-centred as a separate small pool.

This aligned control is a fresh comparison, not a rewrite of the original flat result: the original 0.984152 held-out log loss and its outputs under `out/expected-xi-final/` remain identifiable. Including the shared warm-up columns changes the refreshed flat control to 0.984153. The baseline and fixture coverage are unchanged.

The fixed catalogue still inherits Task 6/7b's **retrospective identity-link assumption**. Links were established using career evidence; they are not archived as-of identity observations. Ratings respect historical availability. The last two seasons are held out for adjustment choices, not an independent overall-model holdout: the global blend, centring design and Task 7b methodology were developed on these seasons.

## Held-out match forecasts

All gains below are baseline loss minus adjusted loss, **×1,000**, positive is better; parentheses contain clustered SEs. Each row has the same 3,500 no-odds fixtures. Each non-baseline row uses its earlier-selected weight. Brier sums the three outcome errors; RPS averages the first two cumulative errors.

| Prior | XI | w | Log loss | Brier | RPS | LL gain (SE) | Brier gain (SE) | RPS gain (SE) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | — | 0 | 0.983295 | 0.585484 | 0.199659 | 0 (0) | 0 (0) | 0 (0) |
| flat | latest | 1 | 0.983562 | 0.585723 | 0.199744 | -0.267 (0.719) | -0.239 (0.502) | -0.085 (0.235) |
| flat | missed | 1 | 0.983707 | 0.585775 | 0.199793 | -0.412 (0.526) | -0.292 (0.369) | -0.134 (0.174) |
| flat | oracle | 1 | 0.983162 | 0.585378 | 0.199582 | +0.133 (0.785) | +0.106 (0.543) | +0.077 (0.253) |
| flat | recent | 2 | 0.984153 | 0.586069 | 0.199978 | -0.858 (0.854) | -0.585 (0.596) | -0.319 (0.281) |
| EA | latest | 0.5 | 0.983214 | 0.585495 | 0.199667 | +0.081 (0.617) | -0.011 (0.432) | -0.008 (0.203) |
| EA | missed | 0.25 | 0.983627 | 0.585706 | 0.199772 | -0.332 (0.269) | -0.222 (0.185) | -0.112 (0.086) |
| EA | oracle | 1 | 0.983264 | 0.585555 | 0.199652 | +0.031 (1.357) | -0.071 (0.940) | +0.007 (0.442) |
| EA | recent | 1 | 0.983740 | 0.585854 | 0.199885 | -0.446 (0.703) | -0.370 (0.498) | -0.225 (0.235) |


EA latest XI has a tiny positive held-out log-loss gain, but earlier seasons selected recent share; switching after seeing the last two seasons would invalidate the check. Its Brier and RPS gains are negative anyway.

### Paired EA against flat

These gains are flat loss minus EA loss, ×1,000 (SE). The same-rule diagnostic fixes both priors to the flat-selected recent-share rule and w = 2, chosen on earlier data. It separates the prior change from the smaller EA-selected weight.

| Comparison | LL gain (SE) | Brier gain (SE) | RPS gain (SE) |
| --- | --- | --- | --- |
| expected | +0.412 (0.587) | +0.215 (0.398) | +0.093 (0.189) |
| oracle | -0.102 (0.942) | -0.176 (0.636) | -0.070 (0.306) |
| same_rule | -1.812 (0.973) | -1.388 (0.676) | -0.717 (0.320) |


The smaller earlier-selected EA weight limits damage. At the same w = 2, EA is worse than flat; no held-out weight or method was used to rescue the result.

### By season, selected expected XI

Gains are ×1,000 (SE). 2015/16–2016/17 are warm-up diagnostics; 2017/18–2023/24 select the weights. Both last seasons retain their frozen choices.

| Season | N | Base LL | Flat LL | EA LL | EA/base LL gain (SE) | EA/flat LL gain (SE) | EA/base Brier gain (SE) | EA/base RPS gain (SE) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2015/16 | 1,824 | 1.000956 | 1.000956 | 1.000956 | +0.000 (0.000) | +0.000 (0.000) | +0.000 (0.000) | +0.000 (0.000) |
| 2016/17 | 1,824 | 0.945032 | 0.945497 | 0.944547 | +0.485 (0.773) | +0.950 (0.753) | +0.432 (0.527) | +0.165 (0.242) |
| 2017/18 | 1,824 | 0.963662 | 0.963908 | 0.963098 | +0.564 (0.796) | +0.810 (0.631) | +0.272 (0.533) | +0.127 (0.254) |
| 2018/19 | 1,826 | 0.978639 | 0.977439 | 0.977910 | +0.729 (0.953) | -0.471 (0.752) | +0.315 (0.634) | +0.270 (0.301) |
| 2019/20 | 1,725 | 0.980651 | 0.981028 | 0.979743 | +0.908 (0.796) | +1.285 (0.795) | +0.602 (0.540) | +0.288 (0.253) |
| 2020/21 | 1,825 | 0.991182 | 0.991296 | 0.990797 | +0.385 (0.804) | +0.499 (0.778) | +0.309 (0.542) | +0.124 (0.260) |
| 2021/22 | 1,826 | 0.989354 | 0.988083 | 0.989131 | +0.224 (0.738) | -1.047 (0.968) | -0.002 (0.492) | +0.066 (0.236) |
| 2022/23 | 1,825 | 0.988676 | 0.986098 | 0.985105 | +3.571 (1.098) | +0.993 (0.712) | +2.481 (0.759) | +1.166 (0.353) |
| 2023/24 | 1,750 | 0.971633 | 0.972207 | 0.971670 | -0.037 (1.123) | +0.538 (0.904) | +0.155 (0.801) | +0.012 (0.375) |
| 2024/25 | 1,750 | 0.975479 | 0.976003 | 0.975479 | +0.000 (1.040) | +0.524 (0.865) | -0.086 (0.734) | -0.159 (0.345) |
| 2025/26 | 1,750 | 0.991110 | 0.992303 | 0.992002 | -0.892 (0.949) | +0.300 (0.794) | -0.654 (0.675) | -0.292 (0.319) |


### By league, last two seasons

| League | N | Base LL | Flat LL | EA LL | EA/base LL gain (SE) | EA/flat LL gain (SE) | EA/base Brier gain (SE) | EA/base RPS gain (SE) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | 610 | 0.985602 | 0.990652 | 0.988401 | -2.799 (1.677) | +2.251 (1.234) | -2.076 (1.196) | -1.035 (0.569) |
| E0 | 760 | 0.996807 | 0.993735 | 0.993654 | +3.152 (1.685) | +0.081 (1.364) | +2.382 (1.199) | +1.066 (0.566) |
| F1 | 611 | 0.983942 | 0.984590 | 0.984769 | -0.827 (2.008) | -0.179 (1.435) | -0.751 (1.418) | -0.304 (0.675) |
| I1 | 760 | 0.981091 | 0.982611 | 0.981733 | -0.642 (1.205) | +0.879 (1.107) | -0.227 (0.843) | -0.315 (0.386) |
| SP1 | 759 | 0.969596 | 0.970525 | 0.971250 | -1.654 (1.286) | -0.725 (1.389) | -1.593 (0.895) | -0.716 (0.423) |


<details>
<summary>League × season: selected expected XI</summary>

Gains are ×1,000 (SE). Full absolute losses and both odds slices are retained in the comparison CSVs.


| League | Season | N | EA/base LL gain (SE) | EA/flat LL gain (SE) | EA/base Brier gain (SE) | EA/base RPS gain (SE) |
| --- | --- | --- | --- | --- | --- | --- |
| D1 | 2015/16 | 306 | +0.000 (0.000) | +0.000 (0.000) | +0.000 (0.000) | +0.000 (0.000) |
| D1 | 2016/17 | 306 | +0.713 (1.685) | +1.415 (1.772) | +0.618 (1.113) | +0.159 (0.498) |
| D1 | 2017/18 | 306 | +1.698 (2.113) | +1.797 (1.655) | +0.757 (1.327) | +0.541 (0.648) |
| D1 | 2018/19 | 306 | -3.973 (3.196) | -3.155 (1.889) | -2.437 (2.121) | -1.101 (1.004) |
| D1 | 2019/20 | 306 | -1.319 (2.062) | -2.005 (1.599) | -0.671 (1.396) | -0.354 (0.617) |
| D1 | 2020/21 | 306 | -0.801 (2.084) | -2.096 (2.093) | -0.767 (1.389) | -0.259 (0.675) |
| D1 | 2021/22 | 306 | +0.204 (1.821) | -3.385 (2.703) | +0.479 (1.201) | +0.241 (0.587) |
| D1 | 2022/23 | 306 | -0.797 (1.967) | -1.210 (1.643) | -0.525 (1.320) | -0.330 (0.566) |
| D1 | 2023/24 | 306 | -0.292 (2.957) | +3.407 (2.378) | +0.609 (2.100) | +0.160 (0.925) |
| D1 | 2024/25 | 304 | -2.023 (2.200) | +1.247 (1.730) | -1.314 (1.528) | -0.658 (0.707) |
| D1 | 2025/26 | 306 | -3.570 (2.556) | +3.249 (1.766) | -2.833 (1.853) | -1.410 (0.896) |
| E0 | 2015/16 | 380 | +0.000 (0.000) | +0.000 (0.000) | +0.000 (0.000) | +0.000 (0.000) |
| E0 | 2016/17 | 380 | -1.338 (2.134) | +0.837 (1.478) | -1.005 (1.467) | -0.379 (0.675) |
| E0 | 2017/18 | 380 | -0.827 (1.690) | +0.580 (1.235) | -0.511 (1.217) | -0.140 (0.563) |
| E0 | 2018/19 | 380 | +0.847 (1.595) | -0.596 (1.981) | +0.484 (1.061) | +0.205 (0.483) |
| E0 | 2019/20 | 380 | +1.516 (1.807) | -0.184 (1.805) | +0.939 (1.203) | +0.438 (0.568) |
| E0 | 2020/21 | 379 | +1.896 (2.147) | +2.739 (1.544) | +1.417 (1.429) | +0.597 (0.699) |
| E0 | 2021/22 | 380 | +1.461 (1.311) | -1.372 (2.101) | +0.927 (0.911) | +0.524 (0.445) |
| E0 | 2022/23 | 380 | +8.276 (2.547) | +2.984 (1.734) | +5.620 (1.750) | +2.802 (0.825) |
| E0 | 2023/24 | 380 | -2.441 (3.246) | -1.750 (2.000) | -2.028 (2.367) | -1.002 (1.128) |
| E0 | 2024/25 | 380 | +6.821 (2.253) | +0.534 (1.840) | +5.014 (1.619) | +2.152 (0.783) |
| E0 | 2025/26 | 380 | -0.516 (2.378) | -0.373 (2.032) | -0.250 (1.676) | -0.019 (0.786) |
| F1 | 2015/16 | 378 | +0.000 (0.000) | +0.000 (0.000) | +0.000 (0.000) | +0.000 (0.000) |
| F1 | 2016/17 | 379 | -0.048 (1.531) | +0.983 (2.059) | +0.033 (1.091) | -0.056 (0.505) |
| F1 | 2017/18 | 378 | +1.410 (2.245) | +1.622 (1.926) | +0.659 (1.505) | +0.166 (0.727) |
| F1 | 2018/19 | 380 | +3.826 (2.031) | +1.801 (1.741) | +2.126 (1.348) | +1.135 (0.654) |
| F1 | 2019/20 | 279 | +1.577 (1.980) | +6.105 (2.433) | +1.415 (1.355) | +0.556 (0.646) |
| F1 | 2020/21 | 380 | -0.588 (1.237) | +0.923 (1.778) | -0.503 (0.892) | -0.251 (0.432) |
| F1 | 2021/22 | 380 | +0.803 (2.018) | +1.410 (1.678) | +0.082 (1.351) | +0.172 (0.640) |
| F1 | 2022/23 | 379 | +2.453 (2.346) | -1.369 (1.447) | +1.707 (1.663) | +0.873 (0.779) |
| F1 | 2023/24 | 306 | +0.374 (2.474) | +2.176 (2.858) | +0.377 (1.771) | +0.204 (0.844) |
| F1 | 2024/25 | 306 | -3.372 (2.964) | +1.674 (1.960) | -2.571 (2.048) | -1.203 (0.976) |
| F1 | 2025/26 | 305 | +1.727 (2.674) | -2.038 (2.082) | +1.076 (1.936) | +0.599 (0.919) |
| I1 | 2015/16 | 380 | +0.000 (0.000) | +0.000 (0.000) | +0.000 (0.000) | +0.000 (0.000) |
| I1 | 2016/17 | 379 | +1.488 (1.835) | -0.039 (1.788) | +0.996 (1.239) | +0.457 (0.573) |
| I1 | 2017/18 | 380 | +0.588 (1.509) | -0.278 (1.184) | +0.256 (1.004) | +0.013 (0.485) |
| I1 | 2018/19 | 380 | +2.871 (2.265) | +0.877 (1.150) | +1.871 (1.514) | +1.171 (0.712) |
| I1 | 2019/20 | 380 | +3.828 (1.705) | +1.977 (1.676) | +2.309 (1.160) | +1.275 (0.573) |
| I1 | 2020/21 | 380 | +1.594 (1.381) | +0.399 (1.553) | +1.075 (0.996) | +0.540 (0.451) |
| I1 | 2021/22 | 380 | -1.508 (1.333) | -1.143 (2.365) | -1.467 (0.834) | -0.629 (0.401) |
| I1 | 2022/23 | 380 | +5.011 (2.501) | +3.090 (1.802) | +3.466 (1.765) | +1.564 (0.805) |
| I1 | 2023/24 | 379 | +2.607 (1.982) | -0.014 (1.132) | +1.935 (1.377) | +0.841 (0.649) |
| I1 | 2024/25 | 380 | -0.826 (1.898) | +0.602 (1.787) | -0.482 (1.359) | -0.476 (0.627) |
| I1 | 2025/26 | 380 | -0.458 (1.507) | +1.155 (1.322) | +0.028 (1.013) | -0.153 (0.457) |
| SP1 | 2015/16 | 380 | +0.000 (0.000) | +0.000 (0.000) | +0.000 (0.000) | +0.000 (0.000) |
| SP1 | 2016/17 | 380 | +1.656 (1.356) | +1.639 (1.288) | +1.555 (0.885) | +0.643 (0.416) |
| SP1 | 2017/18 | 380 | +0.175 (1.341) | +0.523 (0.963) | +0.294 (0.887) | +0.136 (0.407) |
| SP1 | 2018/19 | 380 | -0.842 (1.466) | -1.806 (1.549) | -1.007 (0.989) | -0.327 (0.472) |
| SP1 | 2019/20 | 380 | -1.318 (1.330) | +1.171 (1.289) | -1.014 (0.937) | -0.527 (0.413) |
| SP1 | 2020/21 | 380 | -0.405 (2.039) | +0.029 (1.773) | +0.115 (1.322) | -0.079 (0.635) |
| SP1 | 2021/22 | 380 | +0.154 (1.717) | -1.202 (2.056) | +0.065 (1.145) | +0.056 (0.545) |
| SP1 | 2022/23 | 380 | +2.057 (2.542) | +1.036 (1.169) | +1.550 (1.715) | +0.628 (0.808) |
| SP1 | 2023/24 | 379 | -0.396 (1.703) | -0.257 (1.779) | +0.017 (1.136) | -0.074 (0.548) |
| SP1 | 2024/25 | 380 | -1.660 (2.055) | -1.068 (2.267) | -1.809 (1.416) | -0.914 (0.664) |
| SP1 | 2025/26 | 379 | -1.649 (1.570) | -0.381 (1.629) | -1.375 (1.108) | -0.517 (0.529) |


</details>

### Odds slice

All 3,500 held-out fixtures have complete historical quotes. The 99.9999% saved market weight masks almost all player changes. Selected EA log-loss gain over baseline is **1.53e−10 (SE 6.95e−10)**; EA against flat is **−1.06e−10 (SE 5.76e−10)**. All variants round to baseline log loss **0.970667**. These are numerical-size changes. Quotes retain the original retrospective collection-time approximation, not exact midnight executability.

Odds gains and SEs in this table are **×10⁹**, unlike the no-odds tables.

| Comparison | EA/base LL | EA/base Brier | EA/base RPS | EA/flat LL | EA/flat Brier | EA/flat RPS |
| --- | --- | --- | --- | --- | --- | --- |
| expected | +0.153 (0.695) | +0.100 (0.487) | +0.008 (0.229) | -0.106 (0.576) | -0.107 (0.390) | -0.060 (0.184) |
| oracle | +1.836 (1.347) | +1.183 (0.930) | +0.619 (0.436) | +1.128 (0.927) | +0.702 (0.628) | +0.353 (0.301) |
| same_rule | +0.338 (1.392) | +0.219 (0.976) | +0.025 (0.459) | +0.079 (0.966) | +0.012 (0.669) | -0.043 (0.315) |


## Standings sanity checks

Both priors replay the same thirty origins across 2024/25 and 2025/26, at rounds 5/15/25, with 10,000 simulations and seed 7. Only the next seven days receive the earlier-selected expected-XI adjustment. Unadjusted baseline event scores agree. Means over origins are:

| Prior | Title binary LL | Top-four binary LL | Champion LL |
| --- | --- | --- | --- |
| baseline | 0.047998 | 0.200387 | 0.551922 |
| flat | 0.048097 | 0.199803 | 0.552975 |
| ea | 0.048044 | 0.200372 | 0.552217 |


EA slightly worsens title/champion loss and barely changes top-four loss. These few overlapping season snapshots cannot override the negative match result. The original Jeffreys event-probability smoothing and score-derived final-table caveats are unchanged.

## Reproduce and verify

**Code removed from `main` (24 October 2026).** The experiment was not adopted, so only this report stays. The code is at commit `bb6a1b7`: [`expected_xi.py`](https://github.com/hediblk/football-predictions/blob/bb6a1b7/packages/forecast-calibration/src/forecast_calibration/expected_xi.py) and [`player_prior.py`](https://github.com/hediblk/football-predictions/blob/bb6a1b7/src/standing_prediction/player_prior.py). Check out that commit to run the commands below.

Use the locked environment at base `7b6618d` plus this PR. Both runs make no provider requests:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python -m forecast_calibration.expected_xi \
  --cache-dir /Users/hedibelkahia/codes/football/.cache \
  --out-dir out/expected-xi-flat-aligned
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python -m forecast_calibration.expected_xi \
  --cache-dir /Users/hedibelkahia/codes/football/.cache --prior ea \
  --out-dir out/expected-xi-ea-aligned
```

`--ea-cache` overrides `CACHE_DIR/players`. Each run retains its original per-fixture/per-player files, all weight scores, per-league/per-season tables, ridge choices, selected slopes, standings events and input/code manifest. The EA manifest additionally hashes the identity catalogue, vintage metadata and all 562 compact rating files.

The EA output also contains `compare_priors.py`, `prior_comparison_choices.json`, paired `prior_comparison_scores.csv.gz`, `prior_comparison_overall.csv`, `prior_comparison_by_season.csv`, `prior_comparison_by_league.csv`, `prior_comparison_by_league_season.csv` and `prior_comparison_standings.csv`. Comparison gains use the same league/origin cluster estimator as the main replay. Run the saved comparison script from the repository root after both runs to regenerate these tables.

Verification checked exact fixture/origin alignment, identical no-odds and quoted baselines, unchanged original goal-model/Elo rates and XI predictions, and equal coverage. Both player fits have the same nonzero training basis. The 353 additional EA columns in the final-season audit have no past appearances and retain prior-only coefficients (zero if unrated), with maximum numerical drift **1.5e−15**. Every season's used rating vintages predate its first calibration origin; the latest used 2025/26 vintage is available 4 June 2025, before the 15 August origin. See `comparison_input_audit.json` and `vintage_audit.json`.

The existing offline suite passes **124 tests**, including numerical regressions. No tests, numerical baselines, saved calibration settings or site exports were added or changed by the follow-up. The follow-up automation is disabled after this completed comparison.
