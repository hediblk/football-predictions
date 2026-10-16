# Expected-XI forecast adjustment, 16 October 2026

Offline evaluation for [Task 8](xi-ui-plan-2026-10-15.md#task-8-expected-xi-forecast-adjustment), using the flat-prior, centred starters-only effects from [Task 7](player-impact-xg-plus-minus.md). Nothing in this experiment changes production forecasts, `calibrated_weights.json`, published history or the site. Integration requires a later explicit calibration task, even if an adjustment succeeds here.

**Result: no forecast adjustment with the flat prior.** Earlier seasons selected recent start share with **w = 2**. On 3,500 matched fixtures in 2024/25–2025/26, no-odds log loss rises from **0.983295 to 0.984152**: a gain of **−0.000857 (clustered SE 0.000854)**. Brier and RPS worsen too, and log loss worsens in each held-out season. Latest XI and missed-game decay also fail to improve the pooled last-two-season result. The actual-starters oracle gains only **0.000133 (SE 0.000785)**. That is insufficient evidence for N2 or integration of this particular offset. Better XI probability prediction does not translate into better match probabilities here.

Keep the production weight at zero. Task 7b remains a planned prior comparison; it must repeat the same earlier-only selection and held-out check, preserving this flat-prior result.

## Coverage

The comparison uses **19,749 of 19,763 calibration fixtures**, at **2,257 league-origins**. Ten fixtures lack valid player sheets and four fail the existing result/xG identity, score or date join. All variants, including baseline and oracle, use the same exclusions. There are **39,392** team-games with scorable prior lineup history; **106** no-history sides remain in match scoring with a zero adjustment. Odds exist for 19,748 matched fixtures, including all 3,500 in the last two seasons.

| League | Calibration | Compared | Excluded |
| --- | --- | --- | --- |
| D1 | 3,366 | 3,364 | 2 |
| E0 | 4,180 | 4,179 | 1 |
| F1 | 3,857 | 3,850 | 7 |
| I1 | 4,180 | 4,178 | 2 |
| SP1 | 4,180 | 4,178 | 2 |

## Predicting the XI

All 2015/16–2025/26 covered team-games with usable prior lineup history. Brier is per player; correct is the mean number of actual starters in the predicted top eleven. Parentheses are league/origin-clustered SEs.

### Overall

| method | Team-games | Player Brier (SE) | Correct / 11 (SE) | Start mass |
| --- | --- | --- | --- | --- |
| latest | 39,392 | 0.12566 (0.00076) | 8.293 (0.016) | 11.000 |
| missed | 39,392 | 0.09858 (0.00049) | 8.288 (0.014) | 8.967 |
| recent | 39,392 | 0.09599 (0.00050) | 8.068 (0.013) | 11.000 |

### By league

| league | method | Team-games | Player Brier (SE) | Correct / 11 (SE) | Start mass |
| --- | --- | --- | --- | --- | --- |
| D1 | latest | 6,713 | 0.12046 (0.00162) | 8.520 (0.031) | 11.000 |
| D1 | missed | 6,713 | 0.09789 (0.00112) | 8.461 (0.029) | 9.015 |
| D1 | recent | 6,713 | 0.09689 (0.00118) | 8.177 (0.030) | 11.000 |
| E0 | latest | 8,336 | 0.11617 (0.00150) | 8.734 (0.028) | 11.000 |
| E0 | missed | 8,336 | 0.09575 (0.00099) | 8.668 (0.024) | 9.141 |
| E0 | recent | 8,336 | 0.09563 (0.00095) | 8.368 (0.023) | 11.000 |
| F1 | latest | 7,680 | 0.12278 (0.00168) | 8.238 (0.033) | 11.000 |
| F1 | missed | 7,680 | 0.09662 (0.00121) | 8.217 (0.031) | 8.917 |
| F1 | recent | 7,680 | 0.09407 (0.00125) | 7.991 (0.032) | 11.000 |
| I1 | latest | 8,330 | 0.12509 (0.00153) | 8.085 (0.033) | 11.000 |
| I1 | missed | 8,330 | 0.09572 (0.00099) | 8.133 (0.029) | 8.901 |
| I1 | recent | 8,330 | 0.09217 (0.00101) | 7.956 (0.029) | 11.000 |
| SP1 | latest | 8,333 | 0.14154 (0.00178) | 7.930 (0.038) | 11.000 |
| SP1 | missed | 8,333 | 0.10659 (0.00108) | 7.990 (0.033) | 8.866 |
| SP1 | recent | 8,333 | 0.10156 (0.00106) | 7.862 (0.029) | 11.000 |

### By season

| season | method | Team-games | Player Brier (SE) | Correct / 11 (SE) | Start mass |
| --- | --- | --- | --- | --- | --- |
| 2015/16 | latest | 3,634 | 0.15756 (0.00286) | 8.290 (0.052) | 11.000 |
| 2015/16 | missed | 3,634 | 0.12353 (0.00194) | 8.285 (0.046) | 8.996 |
| 2015/16 | recent | 3,634 | 0.12010 (0.00204) | 8.080 (0.045) | 11.000 |
| 2016/17 | latest | 3,639 | 0.12372 (0.00268) | 8.279 (0.059) | 11.000 |
| 2016/17 | missed | 3,639 | 0.09731 (0.00176) | 8.272 (0.054) | 8.933 |
| 2016/17 | recent | 3,639 | 0.09501 (0.00176) | 8.051 (0.051) | 11.000 |
| 2017/18 | latest | 3,641 | 0.12258 (0.00246) | 8.290 (0.054) | 11.000 |
| 2017/18 | missed | 3,641 | 0.09582 (0.00166) | 8.289 (0.050) | 8.968 |
| 2017/18 | recent | 3,641 | 0.09313 (0.00173) | 8.057 (0.049) | 11.000 |
| 2018/19 | latest | 3,640 | 0.12733 (0.00220) | 8.349 (0.048) | 11.000 |
| 2018/19 | missed | 3,640 | 0.09880 (0.00147) | 8.356 (0.043) | 9.058 |
| 2018/19 | recent | 3,640 | 0.09542 (0.00152) | 8.181 (0.042) | 11.000 |
| 2019/20 | latest | 3,439 | 0.13454 (0.00291) | 8.185 (0.069) | 11.000 |
| 2019/20 | missed | 3,439 | 0.10309 (0.00164) | 8.222 (0.058) | 8.994 |
| 2019/20 | recent | 3,439 | 0.09911 (0.00157) | 8.059 (0.048) | 11.000 |
| 2020/21 | latest | 3,640 | 0.13138 (0.00194) | 8.242 (0.044) | 11.000 |
| 2020/21 | missed | 3,640 | 0.10205 (0.00122) | 8.241 (0.039) | 8.975 |
| 2020/21 | recent | 3,640 | 0.09858 (0.00123) | 8.051 (0.033) | 11.000 |
| 2021/22 | latest | 3,643 | 0.13285 (0.00231) | 8.191 (0.052) | 11.000 |
| 2021/22 | missed | 3,643 | 0.10275 (0.00147) | 8.216 (0.044) | 8.943 |
| 2021/22 | recent | 3,643 | 0.09909 (0.00147) | 8.035 (0.039) | 11.000 |
| 2022/23 | latest | 3,640 | 0.12000 (0.00225) | 8.348 (0.051) | 11.000 |
| 2022/23 | missed | 3,640 | 0.09469 (0.00142) | 8.328 (0.045) | 8.976 |
| 2022/23 | recent | 3,640 | 0.09268 (0.00142) | 8.093 (0.041) | 11.000 |
| 2023/24 | latest | 3,493 | 0.11347 (0.00221) | 8.371 (0.054) | 11.000 |
| 2023/24 | missed | 3,493 | 0.09151 (0.00143) | 8.320 (0.047) | 8.930 |
| 2023/24 | recent | 3,493 | 0.09023 (0.00143) | 8.034 (0.043) | 11.000 |
| 2024/25 | latest | 3,492 | 0.11328 (0.00213) | 8.361 (0.049) | 11.000 |
| 2024/25 | missed | 3,492 | 0.08970 (0.00139) | 8.355 (0.045) | 8.947 |
| 2024/25 | recent | 3,492 | 0.08819 (0.00144) | 8.103 (0.044) | 11.000 |
| 2025/26 | latest | 3,491 | 0.11467 (0.00220) | 8.322 (0.051) | 11.000 |
| 2025/26 | missed | 3,491 | 0.09175 (0.00151) | 8.289 (0.047) | 8.909 |
| 2025/26 | recent | 3,491 | 0.09047 (0.00157) | 8.000 (0.048) | 11.000 |

Recent share improves probability quality while latest XI has the best top-eleven overlap. The missed-game penalty restores nearly the latest-XI overlap but gives away some Brier improvement and leaves about nine expected starters. This is a probability-mass defect of the raw penalty; no unrequested renormalization or injury model was added after seeing the results.

## Match forecasts

### Earlier-only choices

Selection log losses below give equal weight to each league-season, 2017/18–2023/24. These are tuning results, not holdout gains. Both the prior-season ridge and the adjustment choices are frozen before 2024/25; the selected ridge is 300 throughout this replay.

| Method | Selected w | w = 0 log loss | Selected log loss |
| --- | --- | --- | --- |
| latest | 1 | 0.981415 | 0.980985 |
| missed | 1 | 0.981415 | 0.980991 |
| oracle | 1 | 0.981415 | 0.981002 |
| recent | 2 | 0.981415 | 0.980933 |

### Last two seasons, no odds

Lower losses are better. Paired gains below are **×1,000**, positive is better, with clustered SEs in parentheses. Each row has the same 3,500 fixtures. The baseline row is explicitly w = 0.

| Method | w | Log loss | Brier | RPS | LL gain ×1000 (SE) | Brier gain ×1000 (SE) | RPS gain ×1000 (SE) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 0 | 0.983295 | 0.585484 | 0.199659 | +0.000 (0.000) | +0.000 (0.000) | +0.000 (0.000) |
| latest | 1 | 0.983560 | 0.585722 | 0.199744 | -0.265 (0.719) | -0.238 (0.502) | -0.084 (0.235) |
| missed | 1 | 0.983706 | 0.585775 | 0.199793 | -0.411 (0.526) | -0.291 (0.369) | -0.134 (0.174) |
| oracle | 1 | 0.983161 | 0.585378 | 0.199582 | +0.133 (0.785) | +0.106 (0.543) | +0.077 (0.253) |
| recent | 2 | 0.984152 | 0.586068 | 0.199978 | -0.857 (0.854) | -0.584 (0.596) | -0.318 (0.281) |

### By season, no odds

The expected method is recent share (w = 2); the oracle uses w = 1. The first two seasons are warm-up diagnostics; 2017/18–2023/24 select the weight. Gains are ×1,000 (SE).

| Season | N | Base LL | Base Brier | Base RPS | Expected LL gain (SE) | Brier gain (SE) | RPS gain (SE) | Oracle LL gain (SE) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2015/16 | 1,824 | 1.000956 | 0.598728 | 0.204183 | +0.000 (0.000) | +0.000 (0.000) | +0.000 (0.000) | +0.000 (0.000) |
| 2016/17 | 1,824 | 0.945032 | 0.559453 | 0.191743 | -0.336 (0.581) | -0.207 (0.393) | -0.088 (0.176) | +0.593 (0.496) |
| 2017/18 | 1,824 | 0.963662 | 0.572432 | 0.194645 | -0.267 (0.783) | -0.280 (0.530) | -0.117 (0.242) | +0.246 (0.618) |
| 2018/19 | 1,826 | 0.978639 | 0.581920 | 0.196995 | +1.204 (0.885) | +0.570 (0.589) | +0.359 (0.277) | +0.280 (0.805) |
| 2019/20 | 1,725 | 0.980651 | 0.583897 | 0.201234 | -0.377 (0.907) | -0.360 (0.622) | -0.184 (0.280) | +0.537 (0.855) |
| 2020/21 | 1,825 | 0.991182 | 0.590286 | 0.201490 | -0.110 (0.908) | -0.056 (0.617) | -0.005 (0.288) | +0.243 (0.912) |
| 2021/22 | 1,826 | 0.989354 | 0.589574 | 0.200478 | +1.270 (1.002) | +0.778 (0.676) | +0.409 (0.315) | -0.198 (0.914) |
| 2022/23 | 1,825 | 0.988676 | 0.589471 | 0.203276 | +2.581 (1.136) | +1.928 (0.778) | +0.866 (0.352) | +1.860 (0.990) |
| 2023/24 | 1,750 | 0.971633 | 0.578146 | 0.192721 | -0.574 (1.198) | -0.116 (0.857) | -0.121 (0.390) | +0.086 (1.016) |
| 2024/25 | 1,750 | 0.975479 | 0.580421 | 0.197741 | -0.524 (1.160) | -0.285 (0.810) | -0.254 (0.380) | +0.257 (1.131) |
| 2025/26 | 1,750 | 0.991110 | 0.590546 | 0.201577 | -1.191 (1.256) | -0.884 (0.875) | -0.383 (0.416) | +0.010 (1.090) |

### By league, last two seasons, no odds

| League | N | Base LL | Base Brier | Base RPS | Expected LL gain (SE) | Brier gain (SE) | RPS gain (SE) | Oracle LL gain (SE) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | 610 | 0.985602 | 0.585372 | 0.199872 | -5.048 (1.879) | -3.510 (1.331) | -1.693 (0.640) | +1.063 (2.158) |
| E0 | 760 | 0.996807 | 0.595948 | 0.201956 | +3.071 (2.360) | +2.295 (1.679) | +1.109 (0.789) | +3.384 (1.883) |
| F1 | 611 | 0.983942 | 0.586299 | 0.206932 | -0.647 (2.134) | -0.733 (1.470) | -0.243 (0.695) | -0.012 (1.797) |
| I1 | 760 | 0.981091 | 0.585743 | 0.194753 | -1.522 (1.470) | -0.846 (1.009) | -0.662 (0.461) | -2.104 (1.452) |
| SP1 | 759 | 0.969596 | 0.574179 | 0.196246 | -0.927 (1.537) | -0.733 (1.034) | -0.361 (0.496) | -1.511 (1.492) |

Only the Premier League improves for the selected expected method. The Bundesliga reverses more strongly. No league-specific weights were chosen. The oracle is also inconsistent across leagues, despite its small aggregate gain.

<details>
<summary>League × season, no odds: recent share w = 2 and oracle w = 1</summary>

Gains are ×1,000 (SE). Complete absolute losses and paired gains for every selected method, with and without odds, are in `by_league_season.csv`.

| League | Season | N | Expected LL gain (SE) | Brier gain (SE) | RPS gain (SE) | Oracle LL gain (SE) |
| --- | --- | --- | --- | --- | --- | --- |
| D1 | 2015/16 | 306 | +0.000 (0.000) | +0.000 (0.000) | +0.000 (0.000) | +0.000 (0.000) |
| D1 | 2016/17 | 306 | -0.511 (1.397) | -0.431 (0.954) | -0.130 (0.408) | +1.321 (1.177) |
| D1 | 2017/18 | 306 | -0.065 (2.188) | -0.280 (1.451) | +0.005 (0.667) | +1.390 (1.777) |
| D1 | 2018/19 | 306 | -0.821 (2.447) | -1.048 (1.645) | -0.250 (0.789) | +1.075 (1.525) |
| D1 | 2019/20 | 306 | +0.683 (2.278) | +0.600 (1.517) | +0.143 (0.630) | -1.827 (2.352) |
| D1 | 2020/21 | 306 | +1.287 (2.599) | +0.743 (1.780) | +0.418 (0.815) | -1.312 (2.592) |
| D1 | 2021/22 | 306 | +3.586 (3.136) | +2.112 (2.022) | +1.043 (0.960) | +0.044 (2.475) |
| D1 | 2022/23 | 306 | +0.419 (2.990) | +0.538 (1.971) | -0.069 (0.856) | +0.033 (3.173) |
| D1 | 2023/24 | 306 | -3.700 (3.266) | -1.779 (2.330) | -0.862 (0.994) | +2.021 (2.865) |
| D1 | 2024/25 | 304 | -3.271 (2.817) | -2.225 (1.892) | -1.035 (0.886) | +1.612 (3.164) |
| D1 | 2025/26 | 306 | -6.813 (2.495) | -4.788 (1.874) | -2.346 (0.922) | +0.517 (2.979) |
| E0 | 2015/16 | 380 | +0.000 (0.000) | +0.000 (0.000) | +0.000 (0.000) | +0.000 (0.000) |
| E0 | 2016/17 | 380 | -1.863 (1.538) | -1.191 (1.080) | -0.591 (0.470) | -0.253 (1.068) |
| E0 | 2017/18 | 380 | -1.421 (1.886) | -0.729 (1.307) | -0.194 (0.584) | -0.026 (1.133) |
| E0 | 2018/19 | 380 | +1.450 (2.069) | +0.970 (1.377) | +0.413 (0.648) | +1.014 (1.991) |
| E0 | 2019/20 | 380 | +1.690 (1.699) | +1.163 (1.212) | +0.506 (0.571) | +1.002 (1.602) |
| E0 | 2020/21 | 379 | -0.848 (2.161) | -0.143 (1.474) | +0.021 (0.727) | +1.763 (1.964) |
| E0 | 2021/22 | 380 | +2.824 (1.988) | +1.839 (1.394) | +0.810 (0.623) | +2.723 (1.849) |
| E0 | 2022/23 | 380 | +5.304 (3.134) | +3.890 (2.164) | +1.824 (0.978) | +4.453 (1.860) |
| E0 | 2023/24 | 380 | -0.688 (3.167) | -0.437 (2.267) | -0.337 (1.058) | +1.281 (2.284) |
| E0 | 2024/25 | 380 | +6.286 (2.781) | +4.743 (1.997) | +2.077 (0.948) | +6.314 (2.386) |
| E0 | 2025/26 | 380 | -0.143 (3.777) | -0.154 (2.667) | +0.141 (1.254) | +0.453 (2.865) |
| F1 | 2015/16 | 378 | +0.000 (0.000) | +0.000 (0.000) | +0.000 (0.000) | +0.000 (0.000) |
| F1 | 2016/17 | 379 | -0.983 (1.508) | -0.647 (1.018) | -0.373 (0.470) | -1.201 (1.092) |
| F1 | 2017/18 | 378 | -0.227 (1.645) | -0.590 (1.106) | -0.335 (0.472) | +0.297 (1.002) |
| F1 | 2018/19 | 380 | +2.047 (1.636) | +0.892 (1.073) | +0.433 (0.510) | +0.076 (1.647) |
| F1 | 2019/20 | 279 | -4.512 (2.671) | -3.200 (1.844) | -1.513 (0.856) | -1.942 (1.852) |
| F1 | 2020/21 | 380 | -1.513 (2.007) | -1.008 (1.337) | -0.566 (0.651) | -2.157 (1.976) |
| F1 | 2021/22 | 380 | -0.601 (1.786) | -0.734 (1.222) | -0.163 (0.547) | -2.370 (1.365) |
| F1 | 2022/23 | 379 | +3.826 (2.217) | +2.755 (1.532) | +1.372 (0.714) | +4.202 (1.910) |
| F1 | 2023/24 | 306 | -1.801 (2.852) | -0.926 (2.133) | -0.334 (0.983) | +0.810 (2.403) |
| F1 | 2024/25 | 306 | -5.047 (3.036) | -3.731 (2.138) | -1.694 (0.998) | -3.435 (2.734) |
| F1 | 2025/26 | 305 | +3.767 (2.848) | +2.275 (1.916) | +1.214 (0.917) | +3.421 (2.226) |
| I1 | 2015/16 | 380 | +0.000 (0.000) | +0.000 (0.000) | +0.000 (0.000) | +0.000 (0.000) |
| I1 | 2016/17 | 379 | +1.423 (0.867) | +0.883 (0.599) | +0.431 (0.257) | +1.792 (0.950) |
| I1 | 2017/18 | 380 | +0.885 (1.610) | +0.416 (1.051) | +0.116 (0.507) | +1.280 (1.502) |
| I1 | 2018/19 | 380 | +1.991 (2.325) | +1.344 (1.540) | +0.846 (0.716) | -1.712 (2.092) |
| I1 | 2019/20 | 380 | +1.853 (1.952) | +0.990 (1.320) | +0.676 (0.611) | +4.399 (2.084) |
| I1 | 2020/21 | 380 | +1.217 (1.660) | +0.666 (1.135) | +0.349 (0.472) | +0.769 (1.767) |
| I1 | 2021/22 | 380 | -0.360 (2.281) | -0.002 (1.554) | -0.087 (0.740) | -1.025 (2.228) |
| I1 | 2022/23 | 380 | +1.913 (2.080) | +1.305 (1.475) | +0.756 (0.657) | -2.198 (1.894) |
| I1 | 2023/24 | 379 | +2.624 (1.702) | +1.873 (1.201) | +0.906 (0.568) | +0.949 (1.759) |
| I1 | 2024/25 | 380 | -1.429 (2.067) | -0.883 (1.438) | -0.752 (0.664) | -3.753 (2.190) |
| I1 | 2025/26 | 380 | -1.614 (2.114) | -0.809 (1.433) | -0.572 (0.646) | -0.456 (1.901) |
| SP1 | 2015/16 | 380 | +0.000 (0.000) | +0.000 (0.000) | +0.000 (0.000) | +0.000 (0.000) |
| SP1 | 2016/17 | 380 | +0.224 (1.056) | +0.312 (0.643) | +0.215 (0.304) | +1.448 (1.229) |
| SP1 | 2017/18 | 380 | -0.467 (1.566) | -0.218 (1.094) | -0.154 (0.514) | -1.487 (1.509) |
| SP1 | 2018/19 | 380 | +0.958 (1.435) | +0.377 (0.966) | +0.234 (0.442) | +1.101 (1.600) |
| SP1 | 2019/20 | 380 | -2.490 (1.638) | -1.922 (1.117) | -1.020 (0.465) | -0.064 (1.536) |
| SP1 | 2020/21 | 380 | -0.423 (1.841) | -0.383 (1.265) | -0.163 (0.579) | +1.852 (1.984) |
| SP1 | 2021/22 | 380 | +1.353 (2.128) | +0.935 (1.448) | +0.567 (0.680) | -0.313 (2.257) |
| SP1 | 2022/23 | 380 | +1.026 (2.266) | +0.881 (1.531) | +0.267 (0.704) | +2.463 (2.250) |
| SP1 | 2023/24 | 379 | -0.145 (2.338) | +0.214 (1.637) | -0.160 (0.739) | -4.124 (2.100) |
| SP1 | 2024/25 | 380 | -0.587 (2.129) | -0.388 (1.431) | -0.303 (0.684) | +0.097 (2.105) |
| SP1 | 2025/26 | 379 | -1.268 (2.243) | -1.079 (1.510) | -0.418 (0.727) | -3.123 (2.103) |

</details>

### With pre-closing odds

All held-out variants round to log loss **0.970667**, Brier **0.577465** and RPS **0.196084**. The saved 99.9999% market weight almost completely masks the adjustment. Recent share has held-out log-loss gain **2.59e−10 (SE 8.38e−10)**; the oracle has **7.07e−10 (7.75e−10)**. These are numerical-size movements, not evidence of an improvement with odds. The same earlier-selected weights are used; odds do not get a separate tuning pass.

The following marginal tables include the paired SEs for recent share. **Odds gains and SEs are ×10⁹** to make their tiny size visible; they must not be confused with the ×1,000 no-odds tables.

#### By season

| season | N | Base LL | Base Brier | Base RPS | LL gain ×10⁹ (SE) | Brier gain ×10⁹ (SE) | RPS gain ×10⁹ (SE) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2015/16 | 1,824 | 0.982755 | 0.586440 | 0.199005 | +0.000 (0.000) | +0.000 (0.000) | +0.000 (0.000) |
| 2016/17 | 1,824 | 0.932619 | 0.550984 | 0.187852 | +0.270 (0.561) | +0.215 (0.383) | +0.099 (0.169) |
| 2017/18 | 1,824 | 0.946892 | 0.561188 | 0.189890 | +0.298 (0.778) | +0.112 (0.528) | +0.066 (0.238) |
| 2018/19 | 1,826 | 0.962842 | 0.571240 | 0.192300 | +1.401 (0.863) | +0.748 (0.578) | +0.423 (0.271) |
| 2019/20 | 1,725 | 0.975057 | 0.579446 | 0.199196 | +0.186 (0.882) | +0.005 (0.601) | -0.007 (0.269) |
| 2020/21 | 1,825 | 0.981806 | 0.582870 | 0.198324 | +0.668 (0.899) | +0.439 (0.618) | +0.238 (0.287) |
| 2021/22 | 1,825 | 0.977310 | 0.581287 | 0.196544 | +1.956 (1.000) | +1.258 (0.677) | +0.633 (0.314) |
| 2022/23 | 1,825 | 0.977491 | 0.581792 | 0.199851 | +3.047 (1.119) | +2.207 (0.769) | +0.985 (0.346) |
| 2023/24 | 1,750 | 0.955708 | 0.567527 | 0.187874 | +0.326 (1.167) | +0.439 (0.832) | +0.142 (0.376) |
| 2024/25 | 1,750 | 0.963315 | 0.572636 | 0.194372 | +1.093 (1.161) | +0.828 (0.802) | +0.269 (0.378) |
| 2025/26 | 1,750 | 0.978020 | 0.582293 | 0.197796 | -0.575 (1.209) | -0.413 (0.829) | -0.133 (0.391) |

#### By league, last two seasons

| league | N | Base LL | Base Brier | Base RPS | LL gain ×10⁹ (SE) | Brier gain ×10⁹ (SE) | RPS gain ×10⁹ (SE) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | 610 | 0.969641 | 0.575842 | 0.195890 | -4.217 (1.875) | -2.854 (1.336) | -1.389 (0.647) |
| E0 | 760 | 0.992902 | 0.594462 | 0.201332 | +5.045 (2.256) | +3.761 (1.551) | +1.835 (0.726) |
| F1 | 611 | 0.965248 | 0.573168 | 0.201187 | +0.538 (2.076) | +0.071 (1.404) | +0.159 (0.664) |
| I1 | 760 | 0.966016 | 0.575286 | 0.190100 | -0.795 (1.485) | -0.388 (1.016) | -0.459 (0.459) |
| SP1 | 759 | 0.958248 | 0.567389 | 0.192869 | -0.106 (1.507) | -0.183 (1.022) | -0.077 (0.485) |

## Standings sanity checks

Thirty paired origins, ten league-seasons, three origins each. Each cell is baseline → selected recent-share w = 2, averaged over that league-season's three origins. Only the next seven days are adjusted (9–20 fixtures per origin, 316 fixture-snapshot applications). These are descriptive checks; they cannot override the negative match result.

| League | Season | Title binary LL | Top-four binary LL | Champion LL |
| --- | --- | --- | --- | --- |
| D1 | 2024/25 | 0.01438 → 0.01451 | 0.24475 → 0.24411 | 0.13090 → 0.13225 |
| D1 | 2025/26 | 0.00062 → 0.00062 | 0.19488 → 0.19573 | 0.00522 → 0.00522 |
| E0 | 2024/25 | 0.07134 → 0.07137 | 0.08973 → 0.08935 | 0.86631 → 0.86646 |
| E0 | 2025/26 | 0.04660 → 0.04672 | 0.43073 → 0.42562 | 0.48661 → 0.48819 |
| F1 | 2024/25 | 0.01354 → 0.01346 | 0.16439 → 0.16504 | 0.12656 → 0.12572 |
| F1 | 2025/26 | 0.01290 → 0.01302 | 0.25473 → 0.25467 | 0.11817 → 0.11938 |
| I1 | 2024/25 | 0.15274 → 0.15325 | 0.11852 → 0.11831 | 1.95256 → 1.95832 |
| I1 | 2025/26 | 0.05933 → 0.05962 | 0.37855 → 0.37709 | 0.70755 → 0.71082 |
| SP1 | 2024/25 | 0.05076 → 0.05077 | 0.07995 → 0.08043 | 0.53542 → 0.53509 |
| SP1 | 2025/26 | 0.05776 → 0.05760 | 0.04765 → 0.04769 | 0.58992 → 0.58809 |

Across origins, title binary log loss moves **0.047998 → 0.048095**, top-four binary log loss **0.200387 → 0.199805**, and champion log loss **0.551922 → 0.552955**. Changes are small and mixed. There is no standings evidence that rescues the adjustment.

## Protocol

- **Origins and baseline:** reuse `forecast_calibration.dataset.load_season`, including its identity/score/date-checked xG joins, preceding Tuesday/Friday 00:00 UTC origins, E0/SP1/D1/I1/F1 leagues and 2015/16–2025/26 seasons. 2014/15 supplies warm-up history. Results and xG are available the next UTC day after the provider's local match date; only eligible results with kickoff strictly before the origin enter fits. Lineup history uses that same availability boundary, also requiring the Understat kickoff before the origin. Unjoined archive games use next-day availability after their London calendar date. These are retrospective availability approximations, not contemporary publication timestamps.
- **Player fits:** reuse Task 7's team-only xG predictions, centred starters design, expanding prior-season folds and ridge grid. Each player counts as one if starting and zero otherwise, regardless of minutes or later substitutions. Task 7's historical training residuals retain its match-day team-fit convention; every training season ends before the evaluated season. Effects are frozen within each season. Ridge is selected from earlier one-season-ahead xG folds and frozen before 2024/25 for both last seasons; coefficients for 2025/26 may learn from 2024/25, as specified. New players have zero effects under the flat prior. No all-seasons final effect table is used.
- **Expected starts:** use only complete historical sheets in the current and two preceding seasons. The candidate pool contains players who appeared for that team in those eligible games, including substitutes. There is no current-squad join or inferred injury status. Compare latest XI; start share with a three-game half-life; and that share multiplied by `0.5 ** consecutive_nonstarts`. A substitute appearance counts as a nonstart. These constants were fixed before examining this evaluation. The missed-game variant is deliberately the requested raw multiplication: its probabilities need not sum to eleven. The resulting start mass is reported so that this limitation is visible.
- **Usual starts:** the same eligible sheets, weighted by `exp(-0.003 × age_days)`, matching the saved team-model decay and season window. A missing sheet is unknown and never becomes an absence. Team sides without usable history retain a zero adjustment and stay in match scoring; their XI accuracy is unscorable and excluded from that denominator.
- **XI metrics:** per-player binary Brier, pooled across player opportunities; mean correctly predicted starters among the top eleven probabilities. Ties use stable player-ID order. Actual debutants are added to the scoring universe with probability zero, after predictions have been constructed. They never enter expected-XI features. The oracle alone uses actual starters.
- **Weight selection:** nonnegative grid `w = 0, 0.25, 0.5, 1, 2, 4`. Choose one weight per method on 2017/18–2023/24 no-odds log loss, giving every league-season equal weight. Choose the expected method by that same earlier objective, excluding the oracle. Freeze those choices for 2024/25 and 2025/26. The oracle receives its own earlier-selected weight as the hypothetical confirmed-XI ceiling for N2. 2015/16 has no prior-season player training; 2016/17 is ridge warm-up. Both retain match and XI outputs but do not select `w`.
- **Match scoring:** identical covered fixtures and origins for every variant and `w = 0`, including the oracle. Log loss uses the observed home/draw/away outcome; multiclass Brier sums three squared errors; RPS averages the first two cumulative squared errors in home/draw/away order. Lower is better. Gains are baseline loss minus adjusted loss, so positive is better. Tables pool fixtures; only the selection objective balances league-seasons. Standard errors cluster by league and forecast origin, using cluster sums of centred losses or paired gains with the finite-cluster correction. They allow same-origin fixtures to share fit/lineup errors, but do not account for model selection or longer team autocorrelation.
- **Odds:** a separate matched-fixture slice uses the saved blend's odds weight and the calibration dataset's complete pre-closing, de-margined Avg/BbAv/B365 quotes. No closing prices or new quotes are fetched. Historical observation times are only approximated: the provider collected prices in the afternoon whereas the nominal origin is midnight. Consequently these are retrospective market diagnostics, not proof of executable quotes available at midnight. They do not enter no-odds selection.

For team H against A, effects use Task 7's defensive-weakness sign (positive means more conceded):

```text
δattack(team)  = Σ (expected_start − usual_start) × attacking_effect
δdefence(team) = Σ (expected_start − usual_start) × defensive_weakness_effect
λhome' = λhome × exp(w × (δattack(H) + δdefence(A)))
λaway' = λaway × exp(w × (δattack(A) + δdefence(H)))
```

The rates are the existing goal/xG blended Dixon–Coles model's rates. Rebuild its score matrix with unchanged rho, then reuse the production main/Elo/optional-odds blend. Task 7 effects are additive xG estimates; `w` sets their scale as log-rate offsets here. Elo and bookmaker probabilities remain unchanged. At `w = 0` the calculation follows the existing score-matrix and blending functions exactly.

## Reproduce and inspect

Install the existing locked environment and the calibration package, then run from the repository root. The cache directory must contain saved `football-data-uk/` and `understat/` inputs; cache misses fail locally without HTTP requests.

Implementation: [offline evaluation runner](../packages/forecast-calibration/src/forecast_calibration/expected_xi.py).

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python -m forecast_calibration.expected_xi \
  --cache-dir /Users/hedibelkahia/codes/football/.cache \
  --out-dir out/expected-xi-final --n-sim 10000 --seed 7
```

`--reuse` requires an identical manifest of input/code hashes, prior, seed and simulation count. It reuses player fits, fixture features and match scores, then regenerates tables and standings simulations. Outputs stay in ignored `out/expected-xi-final/`:

- `manifest.json`, `summary.json`, `coverage.csv`: provenance, frozen choices and per-league-season exclusions.
- `effects_<season>.csv`, `player_ridge_folds.csv`, `player_ridge_choices.csv`, `player_team_only.csv.gz`: prior-season player fits and ridge selection.
- `xi_probabilities.csv.gz`: each player/team/fixture's usual, latest, recent and missed-game start probabilities and actual start; `xi_predictions.csv.gz` contains team-game accuracy and start mass. `xi_overall.csv`, `xi_by_league.csv`, `xi_by_season.csv`, `xi_by_league_season.csv` summarize them with clustered SEs.
- `features.csv.gz`, `match_scores.csv.gz`, `weight_selection.csv`, `heldout_grid.csv`, `baseline.csv`: rates, signed offsets, every candidate weight's paired scores, selection objective and zero-weight baseline.
- `overall.csv`, `by_league.csv`, `by_season.csv`, `by_league_season.csv`: baseline and selected variants, separated by odds availability, with losses, paired gains and clustered SEs. The league-season table contains the full cross-tabulation.
- `standings.csv`, `standings_events.csv`: snapshot and per-club season-event probabilities.

The prior remains `prior(players, before_season) -> (attack, defence)`. `--prior module:function` plugs in Task 7b's `standing_prediction.player_prior` once merged. Unknown-to-training players request prior-only effects through the same interface. That rerun needs a separate output directory and report comparison; the flat-prior result must remain identifiable.

## Interpretation limits

The last two seasons are held out for this adjustment's weight/method/ridge choices. They are **not an independent overall model holdout**: they influenced the saved global blend and Task 7's decision to centre effects. The baseline is the saved `global-4c0170be18f1` configuration, including xG weight 0.75, scale 1.3, ridge 2 and main/Elo shares approximately 84.42%/15.58% without odds. With odds, the saved market share is 99.9999%, so a player adjustment to the model component can barely move the final probabilities.

The oracle is a ceiling for these particular effects and offsets at the same early origin. It does not evaluate an hour-before-kickoff forecast with updated strengths, injuries or timestamped confirmed-XI archives. Historical lineups and xG come from retrospectively fetched provider payloads. Missing sheets, sparse new-player history, transfers between leagues and unidentified individual effects limit what the flat prior can recover.

Standings replays cover five leagues in 2024/25 and 2025/26, at three Tuesday/Friday origins around rounds 5, 15 and 25. Each run uses the production score simulator, league tie-breaks, identical fixture/team order, 10,000 simulations and seed 7. Only fixtures in the following seven days receive the chosen expected-XI offset; subsequent fixtures use the usual lineup. No future realized lineup enters these simulations. Title and top-four binary log losses average over clubs; champion log loss is also retained separately. Event probabilities use Jeffreys smoothing `(count + 0.5)/(n_sim + 1)` to avoid infinite Monte Carlo-zero losses. Season snapshots overlap, and these ten league-seasons cannot select the adjustment. The retrospective final schedule and score-derived tables are held fixed; historical postponement announcements, sanctions and disciplinary tie-break information are not reconstructed.

## Verification

The run uses base revision `9b86170` plus this PR, Python 3.12.5 and the locked NumPy 2.5.3, pandas 3.0.6 and SciPy 1.18.1, with one numerical worker thread. Two complete runs agree exactly across 31 decompressed CSV artifacts: effects, lineup probabilities, fixture features, every candidate's match scores, summaries, coverage and seeded standings events. The zero-weight goal model reproduces the saved calibration probabilities on all 19,749 compared fixtures within **2.8e−16**; all methods agree exactly at zero weight. Every origin precedes kickoff. `out/expected-xi-final/verification.json` and the repeat-hash files retain these checks.

Focused executable checks also verified that changing future lineups leaves earlier expectations unchanged, unseen players stay out of the feature universe, missed-game decay follows the formula, an unseen-player prior receives the evaluation season and contributes with the correct sign, and no-history sides get zero offsets. The reuse manifest includes the calibration loader, model code, prior and all saved inputs, and is certified only after a complete successful run; interruption removes that certification.

The existing offline suite passed **124 tests**, including numerical regressions:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python -m pytest -q -p no:cacheprovider
```
