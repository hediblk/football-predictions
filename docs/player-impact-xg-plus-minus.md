# Player impact model (xG plus-minus), 16 October 2026

Task 7 of the [squads and players plan](xi-ui-plan-2026-10-15.md). This is an offline experiment with zero forecast weight. No forecast, default, calibration artifact or site file changes.

**Result: yes, but only slightly.** Given the actual lineups, player effects improve later-season team-game xG predictions only when each lineup is measured against the team's usual lineup. Over 32,208 team-games in 2017/18–2025/26, mean squared error falls by **0.0018 xG² (standard error 0.0004)**, from 0.6508 to 0.6490. RMSE falls from 0.8067 to 0.8056 and MAE from 0.6252 to 0.6240. All five leagues and seven of nine seasons improve, and the gain grows with training history. The specified absolute sum (every player's full minutes added on top of pre-game team strengths) gains nothing: its ridge is pushed to the top of the grid, and it ends at −0.00005 (0.00006). Individual player effects are small and poorly identified. None of 8,978 is two posterior standard deviations from zero.

[Task 7b](#task-7b-ea-prior-and-unseen-players-16-october-2026) adds an EA-rating prior and keeps players without training minutes. It roughly doubles the gain overall, but adds nothing in the latest two seasons.

## Data and model

- **Data:** the [Understat match sheets](../data/players/understat/README.md) for five leagues, 2014/15–2025/26: 43,146 team-games and 629,840 appearances for 9,530 players. Excluded matches are absent from both files. The target is each side's match-payload xG (`xg_for`).
- **Team terms (team-only model):** the existing model's fitting code, `standing_prediction.xg.fit_xg_strengths`, with the stored calibration settings: decay 0.003, ridge 2, and the current plus two prior seasons of the same league. It is refitted at 00:00 UTC on every match day from earlier kickoffs only, the domestic played-match refit rule. This gives home advantage, attack and opponent defence from strengths known before the game. The prediction is `exp(intercept + home + attack + opponent defence)`. 2014/15 is warm-up for team strengths only; player rows start in 2015/16.
- **Player terms:** additive xG per 90 on top of the team-only prediction. Each team-game row has the attacking side's lineup in attack columns and the defending side's lineup in defence columns. The coefficients are fitted to the team-only residual by ridge regression (`lsqr`, no intercept). A positive defence coefficient means more xG conceded; the tables below report it as xG prevented.
- **Lineup value:** minutes / 90 in either of two forms:
  - **Absolute (as specified):** every player's minutes / 90.
  - **Centred:** minutes / 90 minus the player's usual minutes / 90 for that team. "Usual" uses the team fit's weights: the same decay, seasons, league and earlier kickoffs. Pre-game team strengths already contain the regulars. Absolute sums count them twice, so a regular's effect can only help where his presence differs from the team's recent games. Centring is equivalent to the specified formula with team terms net of their usual lineup. A promoted side's first game has no usual lineup and enters in absolute form. This is the comparison Task 8 needs ("expected lineup's summed impact minus the team's usual lineup's").
- **Prior:** a flat prior (shrink to zero) until Task 6 adds EA rating vintages. The prior is a pluggable function `prior(players, before_season) -> (attack, defence)` returning prior means in xG per 90. The ridge then shrinks toward those means. A replacement must use only information available before `before_season`.
- **Folds:** for every evaluation season *t* from 2016/17, effects are fitted on all seasons from 2015/16 to *t* − 1 and frozen for season *t*. Team terms keep updating through the season from earlier kickoffs, as the live model does. The ridge strength for season *s* is the grid value (10–30,000) with the lowest pooled MSE over the one-season-ahead folds before *s*. Season 2016/17 only helps choose ridge strengths, so the reported seasons are 2017/18–2025/26.
- **Uncertainty:** posterior standard deviation of the net effect (attack − defence) from the final fit (2015/16–2025/26, ridge 300, residual σ = 0.772). It is computed by conjugate gradients for the 5,653 players with at least 900 training minutes.

Standard errors for the MSE gain treat the two team-games of a match as one cluster. All team-games enter; players unseen in training have zero effect. About 85–88% of evaluation minutes belong to players with training minutes.

## Overall and by season

Centred model; MSE gain is team-only MSE minus player-model MSE, in thousandths of xG² (positive is better). Bias is mean prediction minus actual xG.

| Season | Ridge | Known minutes | Team MAE | Player MAE | Team RMSE | Player RMSE | Team bias | Player bias | MSE gain ×1000 (SE) | Absolute: ridge, gain ×1000 (SE) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2017/18 | 100 | 84.9% | 0.5846 | 0.5858 | 0.7550 | 0.7560 | −0.0016 | +0.0012 | −1.46 (1.60) | 3000, −0.43 (0.36) |
| 2018/19 | 300 | 85.2% | 0.5981 | 0.5966 | 0.7649 | 0.7636 | −0.0568 | −0.0565 | +2.02 (0.78) | 30000, +0.04 (0.04) |
| 2019/20 | 300 | 85.6% | 0.6100 | 0.6096 | 0.7827 | 0.7829 | +0.0059 | +0.0037 | −0.27 (0.86) | 10000, −0.10 (0.19) |
| 2020/21 | 300 | 87.9% | 0.6241 | 0.6236 | 0.8037 | 0.8030 | +0.0092 | +0.0090 | +1.13 (0.92) | 30000, −0.03 (0.06) |
| 2021/22 | 300 | 88.4% | 0.6301 | 0.6295 | 0.8199 | 0.8189 | −0.0251 | −0.0248 | +1.62 (0.95) | 30000, +0.04 (0.06) |
| 2022/23 | 300 | 86.7% | 0.6227 | 0.6214 | 0.8058 | 0.8043 | −0.0224 | −0.0228 | +2.35 (1.02) | 30000, +0.04 (0.06) |
| 2023/24 | 300 | 87.4% | 0.6361 | 0.6337 | 0.8243 | 0.8217 | −0.0540 | −0.0543 | +4.36 (1.15) | 30000, +0.17 (0.07) |
| 2024/25 | 300 | 88.3% | 0.6694 | 0.6662 | 0.8602 | 0.8578 | −0.0061 | −0.0064 | +4.04 (1.24) | 10000, +0.12 (0.24) |
| 2025/26 | 300 | 88.1% | 0.6542 | 0.6521 | 0.8411 | 0.8396 | −0.0169 | −0.0225 | +2.53 (1.21) | 10000, −0.27 (0.20) |
| **All** | | | **0.6252** | **0.6240** | **0.8067** | **0.8056** | **−0.0187** | **−0.0193** | **+1.80 (0.37)** | **−0.05 (0.06)** |

Players do not explain the team-only model's small negative bias. The gain comes from team-games, not from a level shift.

## By league

Centred model, 2017/18–2025/26.

| League | Team-games | Team MAE | Player MAE | Team RMSE | Player RMSE | Team bias | Player bias | MSE gain ×1000 (SE) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Premier League | 6,838 | 0.6339 | 0.6324 | 0.8160 | 0.8137 | −0.0237 | −0.0234 | +3.75 (0.86) |
| Ligue 1 | 6,188 | 0.6201 | 0.6188 | 0.8010 | 0.8000 | −0.0234 | −0.0243 | +1.54 (0.78) |
| Bundesliga | 5,506 | 0.6688 | 0.6670 | 0.8646 | 0.8637 | −0.0265 | −0.0297 | +1.51 (0.95) |
| Serie A | 6,840 | 0.6009 | 0.6002 | 0.7710 | 0.7701 | −0.0001 | −0.0005 | +1.34 (0.76) |
| La Liga | 6,836 | 0.6102 | 0.6095 | 0.7890 | 0.7885 | −0.0218 | −0.0211 | +0.79 (0.79) |

<details>
<summary>By league and season (centred; team / player)</summary>

| League | Season | Team-games | MAE | RMSE | Bias | MSE gain ×1000 (SE) |
| :--- | :--- | ---: | :--- | :--- | :--- | ---: |
| Bundesliga | 2017/18 | 612 | 0.592 / 0.591 | 0.750 / 0.752 | +0.013 / +0.006 | −2.38 (4.38) |
| Bundesliga | 2018/19 | 612 | 0.650 / 0.648 | 0.853 / 0.852 | −0.158 / −0.160 | +1.51 (2.13) |
| Bundesliga | 2019/20 | 612 | 0.695 / 0.694 | 0.863 / 0.864 | +0.012 / +0.011 | −0.44 (2.07) |
| Bundesliga | 2020/21 | 612 | 0.635 / 0.635 | 0.814 / 0.813 | +0.072 / +0.072 | +1.25 (2.29) |
| Bundesliga | 2021/22 | 612 | 0.679 / 0.677 | 0.915 / 0.913 | −0.043 / −0.047 | +3.94 (2.70) |
| Bundesliga | 2022/23 | 612 | 0.678 / 0.676 | 0.884 / 0.884 | +0.006 / +0.004 | +1.14 (3.19) |
| Bundesliga | 2023/24 | 612 | 0.669 / 0.668 | 0.864 / 0.864 | −0.052 / −0.056 | +0.23 (3.15) |
| Bundesliga | 2024/25 | 610 | 0.707 / 0.703 | 0.887 / 0.883 | −0.007 / −0.009 | +6.39 (2.46) |
| Bundesliga | 2025/26 | 612 | 0.714 / 0.712 | 0.937 / 0.936 | −0.082 / −0.088 | +1.94 (2.59) |
| Premier League | 2017/18 | 760 | 0.569 / 0.570 | 0.750 / 0.749 | −0.027 / −0.020 | +0.40 (2.98) |
| Premier League | 2018/19 | 760 | 0.597 / 0.596 | 0.755 / 0.754 | −0.067 / −0.064 | +2.17 (1.82) |
| Premier League | 2019/20 | 760 | 0.619 / 0.617 | 0.806 / 0.804 | +0.002 / +0.003 | +3.05 (1.69) |
| Premier League | 2020/21 | 758 | 0.628 / 0.627 | 0.805 / 0.804 | +0.027 / +0.024 | +1.73 (2.22) |
| Premier League | 2021/22 | 760 | 0.630 / 0.629 | 0.792 / 0.790 | −0.025 / −0.026 | +2.76 (2.23) |
| Premier League | 2022/23 | 760 | 0.626 / 0.624 | 0.822 / 0.819 | −0.060 / −0.057 | +5.14 (2.43) |
| Premier League | 2023/24 | 760 | 0.696 / 0.694 | 0.897 / 0.895 | −0.105 / −0.105 | +4.50 (2.89) |
| Premier League | 2024/25 | 760 | 0.682 / 0.679 | 0.880 / 0.876 | +0.045 / +0.050 | +7.29 (3.28) |
| Premier League | 2025/26 | 760 | 0.659 / 0.655 | 0.824 / 0.820 | −0.004 / −0.017 | +6.69 (3.21) |
| La Liga | 2017/18 | 760 | 0.604 / 0.608 | 0.793 / 0.795 | −0.061 / −0.045 | −3.48 (4.16) |
| La Liga | 2018/19 | 760 | 0.608 / 0.607 | 0.781 / 0.779 | −0.026 / −0.025 | +3.15 (1.50) |
| La Liga | 2019/20 | 760 | 0.586 / 0.586 | 0.732 / 0.733 | +0.063 / +0.053 | −0.48 (1.69) |
| La Liga | 2020/21 | 760 | 0.619 / 0.619 | 0.800 / 0.801 | +0.020 / +0.017 | −1.27 (1.90) |
| La Liga | 2021/22 | 760 | 0.602 / 0.600 | 0.802 / 0.801 | −0.035 / −0.033 | +2.08 (1.92) |
| La Liga | 2022/23 | 760 | 0.605 / 0.603 | 0.776 / 0.774 | −0.061 / −0.062 | +2.66 (1.97) |
| La Liga | 2023/24 | 758 | 0.611 / 0.608 | 0.782 / 0.780 | −0.046 / −0.047 | +3.50 (2.21) |
| La Liga | 2024/25 | 760 | 0.642 / 0.640 | 0.836 / 0.835 | −0.014 / −0.016 | +1.59 (2.64) |
| La Liga | 2025/26 | 758 | 0.615 / 0.616 | 0.794 / 0.795 | −0.036 / −0.032 | −0.66 (2.25) |
| Ligue 1 | 2017/18 | 758 | 0.567 / 0.569 | 0.741 / 0.742 | −0.002 / −0.000 | −1.04 (2.81) |
| Ligue 1 | 2018/19 | 760 | 0.567 / 0.566 | 0.716 / 0.715 | −0.016 / −0.019 | +1.27 (1.55) |
| Ligue 1 | 2019/20 | 558 | 0.565 / 0.565 | 0.731 / 0.732 | +0.029 / +0.025 | −1.80 (2.06) |
| Ligue 1 | 2020/21 | 760 | 0.617 / 0.616 | 0.804 / 0.803 | −0.027 / −0.025 | +2.00 (1.87) |
| Ligue 1 | 2021/22 | 760 | 0.608 / 0.610 | 0.780 / 0.782 | −0.047 / −0.044 | −2.41 (1.86) |
| Ligue 1 | 2022/23 | 758 | 0.634 / 0.633 | 0.819 / 0.818 | −0.071 / −0.069 | +1.06 (1.94) |
| Ligue 1 | 2023/24 | 612 | 0.611 / 0.607 | 0.804 / 0.799 | −0.028 / −0.028 | +8.01 (2.59) |
| Ligue 1 | 2024/25 | 612 | 0.739 / 0.734 | 0.946 / 0.944 | −0.081 / −0.084 | +4.20 (3.06) |
| Ligue 1 | 2025/26 | 610 | 0.694 / 0.689 | 0.869 / 0.866 | +0.048 / +0.038 | +3.88 (3.09) |
| Serie A | 2017/18 | 760 | 0.593 / 0.592 | 0.739 / 0.740 | +0.071 / +0.067 | −0.99 (3.59) |
| Serie A | 2018/19 | 760 | 0.578 / 0.576 | 0.729 / 0.728 | −0.037 / −0.035 | +1.89 (1.76) |
| Serie A | 2019/20 | 760 | 0.590 / 0.591 | 0.777 / 0.778 | −0.070 / −0.067 | −2.12 (2.13) |
| Serie A | 2020/21 | 760 | 0.623 / 0.623 | 0.797 / 0.796 | −0.033 / −0.031 | +1.95 (1.99) |
| Serie A | 2021/22 | 760 | 0.641 / 0.641 | 0.822 / 0.821 | +0.020 / +0.021 | +2.19 (2.01) |
| Serie A | 2022/23 | 760 | 0.582 / 0.581 | 0.736 / 0.735 | +0.080 / +0.075 | +1.50 (2.02) |
| Serie A | 2023/24 | 760 | 0.595 / 0.593 | 0.771 / 0.767 | −0.034 / −0.030 | +5.45 (2.07) |
| Serie A | 2024/25 | 760 | 0.598 / 0.597 | 0.765 / 0.764 | +0.012 / +0.011 | +1.23 (2.24) |
| Serie A | 2025/26 | 760 | 0.608 / 0.608 | 0.798 / 0.797 | −0.011 / −0.016 | +0.94 (2.25) |

34 of 45 league-seasons improve.

</details>

## Ridge strength

One-season-ahead MSE gain ×1000 for every ridge strength in the centred model. The prior standard deviation per effect is σ / √ridge: about 0.045 xG per 90 at 300.

| Season | 10 | 30 | 100 | 300 | 1000 | 3000 | 10000 | 30000 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2016/17 | −42.54 | −6.95 | +1.15 | +1.13 | +0.46 | +0.17 | +0.05 | +0.02 |
| 2017/18 | −63.81 | −15.73 | −1.46 | +0.40 | +0.28 | +0.11 | +0.04 | +0.01 |
| 2018/19 | −55.42 | −10.64 | +1.73 | +2.02 | +0.88 | +0.33 | +0.10 | +0.03 |
| 2019/20 | −76.82 | −24.06 | −4.15 | −0.27 | +0.15 | +0.08 | +0.03 | +0.01 |
| 2020/21 | −50.89 | −12.93 | −0.21 | +1.13 | +0.58 | +0.22 | +0.07 | +0.02 |
| 2021/22 | −59.82 | −15.22 | −0.01 | +1.62 | +0.83 | +0.32 | +0.10 | +0.03 |
| 2022/23 | −63.22 | −15.30 | +1.05 | +2.35 | +1.13 | +0.44 | +0.14 | +0.05 |
| 2023/24 | −45.65 | −4.23 | +5.96 | +4.36 | +1.80 | +0.67 | +0.21 | +0.07 |
| 2024/25 | −53.55 | −8.25 | +4.71 | +4.04 | +1.74 | +0.65 | +0.20 | +0.07 |
| 2025/26 | −79.48 | −20.70 | +0.14 | +2.53 | +1.33 | +0.52 | +0.17 | +0.06 |

Earlier folds chose 100 for 2017/18 (from 2016/17 alone) and 300 for every later season. Each season's choice uses only earlier folds. A weak ridge overfits badly. The absolute model is worse than team-only at every ridge of 300 or less in every fold except 2023/24 at 300. Its selected ridges of 3,000–30,000 effectively switch the player terms off.

## Learning curves

Centred model, ridge as selected for that season. The latest three seasons are each fitted on only their *k* most recent prior seasons. Values are MSE gain ×1000 (SE).

| Training seasons | 2023/24 | 2024/25 | 2025/26 |
| ---: | ---: | ---: | ---: |
| 1 | +1.14 (0.62) | +1.62 (0.64) | −0.01 (0.61) |
| 2 | +2.27 (0.83) | +2.78 (0.86) | +1.35 (0.82) |
| 3 | +2.97 (0.94) | +2.97 (0.97) | +0.83 (0.94) |
| 4 | +3.87 (1.01) | +3.13 (1.01) | +1.27 (1.01) |
| 5 | +3.80 (1.08) | +3.49 (1.12) | +1.47 (1.08) |
| 6 | +4.00 (1.10) | +3.71 (1.17) | +1.57 (1.12) |
| 7 | +4.31 (1.11) | +4.00 (1.20) | +2.43 (1.17) |
| 8 | +4.36 (1.15) | +4.18 (1.21) | +2.26 (1.17) |
| 9 | — | +4.04 (1.24) | +2.47 (1.19) |
| 10 | — | — | +2.53 (1.21) |

The gain grows with history for about four seasons and then flattens. The expanding-window table above shows the same pattern across seasons. Effects are not time-weighted, so a player's 2015 games count as much as his last season's.

## Largest player effects

Centred model, all seasons 2015/16–2025/26, ridge 300. Effects are xG per 90 relative to the team's usual lineup. Net = attack + prevented. The interval is ± one posterior standard deviation. Club and season are the player's latest appearance. **With-or-without** is a sanity check only, never the estimate. It is the team-only residual net xG per game (for minus against) with the player on for 45+ minutes, minus games he missed in the same club-seasons (games with/without). It ignores team-mates and opponents, and selecting the largest effects inflates it.

| # | Player | Club (latest) | Position | Minutes | Attack | Prevented | Net | With-or-without (games) |
| ---: | :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| 1 | Djibril Sidibe | Toulouse (2025/26) | DR | 18,917 | +0.035 | +0.075 | +0.110 ± 0.055 | +0.30 (209/82) |
| 2 | Bruno Guimarães | Newcastle United (2025/26) | MC | 16,553 | +0.064 | +0.043 | +0.106 ± 0.059 | +0.56 (188/85) |
| 3 | Nick Pope | Newcastle United (2025/26) | GK | 22,205 | +0.026 | +0.072 | +0.099 ± 0.057 | +0.48 (247/56) |
| 4 | Xaver Schlager | RasenBallsport Leipzig (2025/26) | DMC | 11,471 | +0.055 | +0.043 | +0.097 ± 0.058 | +0.65 (130/88) |
| 5 | Henrikh Mkhitaryan | Inter (2025/26) | MC | 23,061 | +0.061 | +0.032 | +0.093 ± 0.055 | +0.39 (261/165) |
| 6 | Perparim Hetemaj | Benevento (2020/21) | MC | 10,963 | +0.013 | +0.077 | +0.090 ± 0.060 | +0.88 (127/46) |
| 7 | Joe Hart | Burnley (2018/19) | GK | 9,772 | −0.033 | −0.054 | −0.086 ± 0.058 | −0.49 (109/43) |
| 8 | Raphael Guerreiro | Bayern Munich (2025/26) | DL | 18,201 | +0.051 | +0.035 | +0.086 ± 0.056 | +0.30 (206/121) |
| 9 | Mohamed Salah | Liverpool (2025/26) | FWR | 31,643 | +0.087 | −0.005 | +0.082 ± 0.057 | +0.35 (357/38) |
| 10 | Philipp Lienhart | Freiburg (2025/26) | DC | 17,004 | +0.035 | +0.046 | +0.081 ± 0.058 | +0.52 (191/97) |
| 11 | Rodrigo Bentancur | Tottenham (2025/26) | MC | 15,742 | +0.039 | +0.041 | +0.080 ± 0.057 | +0.36 (182/137) |
| 12 | Benjamin Lecomte | Montpellier (2024/25) | GK | 25,740 | +0.027 | +0.052 | +0.079 ± 0.056 | +0.32 (286/74) |
| 13 | Weston McKennie | Juventus (2025/26) | MC | 18,383 | +0.043 | +0.036 | +0.079 ± 0.056 | +0.21 (203/136) |
| 14 | Abdoulaye Doucouré | Everton (2024/25) | MC | 24,757 | +0.043 | +0.036 | +0.079 ± 0.055 | +0.40 (279/109) |
| 15 | Julian Ryerson | Borussia Dortmund (2025/26) | DMR | 11,671 | +0.041 | +0.038 | +0.079 ± 0.058 | +0.42 (129/95) |
| 16 | Marc Guehi | Manchester City (2025/26) | DC | 14,788 | +0.037 | +0.042 | +0.078 ± 0.059 | +0.42 (164/61) |
| 17 | Virgil van Dijk | Liverpool (2025/26) | DC | 30,173 | +0.039 | +0.038 | +0.077 ± 0.057 | +0.14 (336/117) |
| 18 | Jorginho | Arsenal (2024/25) | MC | 21,389 | +0.020 | +0.057 | +0.077 ± 0.056 | +0.23 (248/127) |
| 19 | Jonas Hofmann | Bayer Leverkusen (2025/26) | AMC | 16,681 | +0.036 | +0.041 | +0.077 ± 0.056 | +0.22 (188/151) |
| 20 | Divock Origi | Nottingham Forest (2023/24) | FW | 6,932 | −0.055 | −0.021 | −0.076 ± 0.059 | −0.70 (70/191) |

The with-or-without split agrees in sign for all 20 and is two to ten times larger, as expected from an unadjusted, selected comparison.

## Most uncertain effects

The 20 largest posterior standard deviations among the 5,653 players with at least 900 training minutes:

| # | Player | Club (latest) | Position | Minutes | Net | Posterior SD |
| ---: | :--- | :--- | :--- | ---: | ---: | ---: |
| 1 | Patrick Mainka | FC Heidenheim (2025/26) | DC | 9,180 | −0.005 | 0.063 |
| 2 | Neil Etheridge | Cardiff (2018/19) | GK | 3,420 | −0.003 | 0.063 |
| 3 | Thomas Kaminski | Luton (2023/24) | GK | 3,410 | −0.006 | 0.063 |
| 4 | Nikola Vasilj | St. Pauli (2025/26) | GK | 6,030 | −0.004 | 0.063 |
| 5 | Régis Gurtner | Amiens (2019/20) | GK | 9,270 | −0.001 | 0.063 |
| 6 | Zuriko Davitashvili | Saint-Etienne (2024/25) | FWL | 2,815 | −0.010 | 0.063 |
| 7 | Roberto Trashorras | Rayo Vallecano (2015/16) | DMC | 3,119 | +0.001 | 0.063 |
| 8 | Simone Canestrelli | Pisa (2025/26) | DC | 3,200 | +0.006 | 0.063 |
| 9 | Alfie Doughty | Luton (2023/24) | DML | 2,980 | +0.005 | 0.063 |
| 10 | Ransford Königsdörffer | Hamburger SV (2025/26) | FW | 2,425 | +0.000 | 0.063 |
| 11 | Gustavo Hamer | Sheffield United (2023/24) | MC | 2,986 | −0.008 | 0.063 |
| 12 | Stefan Schimmer | FC Heidenheim (2025/26) | FW | 1,074 | −0.006 | 0.063 |
| 13 | Cristian Buonaiuto | Cremonese (2022/23) | AMC | 957 | −0.005 | 0.063 |
| 14 | Tim Leibold | Nuernberg (2018/19) | DL | 2,773 | +0.008 | 0.063 |
| 15 | Marvin Matip | Ingolstadt (2016/17) | DC | 5,893 | +0.013 | 0.063 |
| 16 | Christopher Schindler | Huddersfield (2018/19) | DC | 6,535 | +0.003 | 0.063 |
| 17 | Trai Hume | Sunderland (2025/26) | DR | 3,041 | +0.002 | 0.063 |
| 18 | Robin Roefs | Sunderland (2025/26) | GK | 3,150 | −0.010 | 0.063 |
| 19 | Mamadou Diakhon | Reims (2024/25) | FWL | 976 | −0.006 | 0.063 |
| 20 | Alimami Gory | Paris FC (2025/26) | DR | 959 | −0.002 | 0.063 |

These are ever-present players at promoted or short-lived top-flight sides. Their minutes barely differ from the usual lineup, so the data hardly moves them from the prior: 0.063 is the flat prior's net standard deviation. Uncertainty follows how often a player's presence changes, not his total minutes. Across all 5,653 players the posterior SD ranges only from 0.053 to 0.063 (median 0.061). No net effect is two posterior SDs from zero, and only five exceed 1.645.

## Interpretation and limits

- **The signal is collective.** Individually, effects are within noise. Together, the lineup still predicts xG beyond pre-game team strengths, through absences and rotation. Most leading effects have similar attack and prevented parts. Goalkeepers rank high (Pope, Lecomte, Neuer just below the top 20), which suggests that "first-choice side against rotated side" is part of what the effects pick up. These are not clean individual skill estimates.
- **Given actual lineups.** Evaluation conditions on observed minutes, including in-game substitutions and red cards, which respond to the score. A **starters-only** variant (`--lineup starters`: a start counts as 90 minutes, a substitute appearance as none, centred the same way) uses only what is known at kickoff. It keeps most of the gain: **+1.60 (0.38)** overall against +1.80 (0.37), positive in eight of nine seasons, with the Premier League again largest (+3.77, SE 0.89). So the signal is the starting XI, not in-game substitutions or red cards. This is the gain a confirmed XI could deliver. Task 8 must still measure what an expected XI, predicted days ahead, keeps.
- **Scale.** A 0.0018 MSE reduction is 0.28% of team-only MSE. Whether that survives into match log loss once the lineup has to be predicted is Task 8's question, not this one's.
- **Absolute against centred.** The specified absolute form, with team terms from pre-game strengths, double-counts regulars and is never better than team-only. Task 8's "expected lineup minus usual lineup" offset is the centred form.
- **Timing.** Results follow the README: retrospective match sheets, with xG assumed available by the end of the match's UTC day. Ridge strengths come from earlier folds only, but 2017/18–2025/26 also shaped this design: the decision to centre was taken after seeing the absolute results on the same seasons. Treat the centred numbers as a strong replay, not an untouched holdout.
- **Not yet tried:** time-weighting player games, ageing, position-specific priors and the EA prior (Task 6). Coverage of new players (12–15% of evaluation minutes have zero effect) is where the EA prior should help most.

## Task 7b: EA prior and unseen players (16 October 2026)

**Result: the EA prior roughly doubles the gain, but not in the latest two seasons.** With EA ratings as the shrinkage target, the centred lineup's MSE gain over team-only rises from +1.80 to **+4.26 (0.68)** ×1000. The starters lineup rises from +1.60 to **+3.03 (0.61)**. Against the flat prior on the same team-games, the EA prior adds +2.46 (0.54) for centred and +1.43 (0.44) for starters. It helps in all five leagues. It also helps in eight of nine seasons for centred and six of nine for starters. It does not help reliably in the latest two: in 2024/25 and 2025/26 the differences run from −0.88 to +0.56 ×1000, each within its standard error. New players' own contributions are worth +0.57 (0.22). Most of the gain comes from a better shrinkage target for players who already have minutes. The first version, which rated every training season with the evaluation season's ratings, made things worse; see "Hindsight ratings" below.

### What changed

- **Unseen players.** Fold columns now include every evaluation-season player. A player without training rows has only his prior mean, so his minutes count once the prior is informative. With the flat prior that mean is zero, and Task 7's numbers reproduce exactly. "Unseen" means no nonzero entry in the training design: 11–15% of evaluation minutes.
- **EA prior** (`player_prior.py` at commit `bb6a1b7`, `EaPrior`). The prior mean is slope × (EA overall − position-group mean), with one slope for attack and one for defence. Groups are GK, DEF, MID and ATT, from the first listed EA position. The group mean is taken over the fold's rated players. Ratings use `matched` rows of `data/players/understat_ea_links.csv`. Each player gets the latest vintage in `data/players/ea/vintages.json` with `available_from` before the season's first kickoff (across the five leagues) that lists him, looking back at most 365 days. Unlinked and unrated players get 0. The callable keeps Task 7's signature, `prior(players, before_season) -> (attack, defence)`, once its slopes are fitted, so Task 8 can import it.
- **Slopes from earlier seasons only.** The slopes are fitted on the training seasons, jointly with the ridge: unpenalised on the two prior directions, by profiling out the ridge (Frisch–Waugh). Regressing already-shrunk effects on ratings would attenuate them. Each training row uses the ratings available before **its own** season, which is how evaluation uses them. The fitted model is therefore effect = slope × rating(season) + a constant per-player deviation. The deviation is shrunk to zero, and the rating part moves with each new vintage.
- **Ridge re-chosen** on earlier folds for each prior. The EA prior chose 300 every season for centred; for starters it chose 300, except 1,000 for 2021/22. The flat prior chose 300 except 100 for centred 2017/18, as before.

### Overall

Evaluation seasons 2017/18–2025/26, 32,208 team-games, given lineups. MSE gains are ×1000 xG² against team-only, with match-clustered standard errors; positive is better. The last column compares the two priors on identical team-games.

| Lineup | Prior | MAE | RMSE | Bias | Gain vs team-only | EA − flat |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| — | Team only | 0.6252 | 0.8067 | −0.0187 | | |
| Centred | Flat | 0.6240 | 0.8056 | −0.0193 | +1.80 (0.37) | |
| Centred | EA | **0.6233** | **0.8041** | −0.0125 | **+4.26 (0.68)** | **+2.46 (0.54)** |
| Starters | Flat | 0.6239 | 0.8057 | −0.0202 | +1.60 (0.38) | |
| Starters | EA | 0.6236 | 0.8048 | −0.0153 | +3.03 (0.61) | +1.43 (0.44) |

The EA prior also reduces the team-only model's small under-prediction.

### By season

| Season | Centred, flat | Centred, EA | Centred, EA − flat | Starters, flat | Starters, EA | Starters, EA − flat |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2017/18 | −1.49 (1.60) | +4.15 (1.73) | +5.65 (1.76) | +0.29 (0.74) | +3.65 (1.47) | +3.36 (1.25) |
| 2018/19 | +2.02 (0.78) | +5.99 (1.86) | +3.96 (1.56) | +1.40 (0.85) | +4.47 (1.67) | +3.07 (1.32) |
| 2019/20 | −0.27 (0.86) | +0.63 (1.88) | +0.90 (1.61) | −0.07 (1.01) | −0.17 (1.79) | −0.10 (1.39) |
| 2020/21 | +1.14 (0.92) | +4.98 (1.92) | +3.85 (1.49) | +0.53 (1.07) | +2.63 (1.83) | +2.10 (1.26) |
| 2021/22 | +1.62 (0.95) | +3.30 (1.89) | +1.68 (1.47) | +1.60 (1.12) | +2.40 (1.37) | +0.80 (1.36) |
| 2022/23 | +2.35 (1.02) | +5.68 (2.09) | +3.33 (1.59) | +1.47 (1.18) | +3.12 (1.95) | +1.65 (1.27) |
| 2023/24 | +4.36 (1.15) | +7.19 (2.23) | +2.83 (1.67) | +4.16 (1.34) | +6.53 (2.05) | +2.37 (1.32) |
| 2024/25 | +4.04 (1.24) | +3.16 (2.49) | −0.88 (1.90) | +3.36 (1.37) | +3.01 (2.19) | −0.35 (1.51) |
| 2025/26 | +2.53 (1.21) | +3.09 (2.11) | +0.56 (1.52) | +1.74 (1.43) | +1.50 (2.05) | −0.24 (1.23) |

The flat prior's gain grows with training history, while the EA prior's does not: the EA prior matters most when there are few minutes to learn from. In the latest two seasons the flat prior has caught up. Those seasons also have the thinnest rating vintages: 2024/25 uses FC 24's single September 2023 snapshot, 11 months old at kickoff. The vintage table and coverage are in [the EA README](../data/players/ea/README.md). Task 8 should not assume the EA prior helps a current-season forecast more than the flat prior. Its averaged gain is driven by earlier seasons.

### By league

| League | Team-games | Centred, flat | Centred, EA | Centred, EA − flat | Starters, flat | Starters, EA | Starters, EA − flat |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Premier League | 6,838 | +3.74 (0.86) | +7.59 (1.65) | +3.86 (1.22) | +3.77 (0.89) | +6.13 (1.44) | +2.36 (0.97) |
| Bundesliga | 5,506 | +1.53 (0.95) | +4.49 (1.63) | +2.96 (1.33) | +1.35 (1.00) | +2.82 (1.53) | +1.48 (1.11) |
| La Liga | 6,836 | +0.77 (0.79) | +3.08 (1.39) | +2.31 (1.16) | +0.54 (0.78) | +1.64 (1.25) | +1.10 (0.93) |
| Ligue 1 | 6,188 | +1.53 (0.78) | +3.09 (1.56) | +1.56 (1.29) | +1.51 (0.80) | +2.88 (1.38) | +1.37 (1.05) |
| Serie A | 6,840 | +1.35 (0.76) | +2.98 (1.33) | +1.63 (1.08) | +0.77 (0.79) | +1.61 (1.24) | +0.84 (0.90) |

### Unseen players

"Unseen only" adds only the unseen players' contributions to the team-only prediction. It is zero by construction under the flat prior. "Matches with unseen minutes" are matches where unseen players played at least 90 minutes across both sides: 25,330 team-games for centred and 27,912 for starters. Team-games with fewer unseen minutes are listed separately.

| | Centred | Starters |
| :--- | ---: | ---: |
| Unseen only, EA prior, all team-games | +0.57 (0.22) | +0.49 (0.20) |
| Matches with unseen minutes: flat | +1.78 (0.40) | +1.35 (0.40) |
| Matches with unseen minutes: EA | +4.57 (0.78) | +3.19 (0.66) |
| Matches with unseen minutes: EA − flat | +2.78 (0.63) | +1.84 (0.49) |
| Other team-games: EA − flat | +1.29 (1.02) | −1.25 (0.96) |

By season, the unseen-only gain for centred is positive in seven of nine seasons, between −0.43 and +1.55. It is in `unseen.csv`.

| Season | Unseen minutes share | Rated, all minutes | Rated, unseen minutes |
| :--- | ---: | ---: | ---: |
| 2017/18 | 13.8% | 97.9% | 87.0% |
| 2018/19 | 13.9% | 98.7% | 93.1% |
| 2019/20 | 14.2% | 98.2% | 90.4% |
| 2020/21 | 11.9% | 97.1% | 83.0% |
| 2021/22 | 11.5% | 97.1% | 83.7% |
| 2022/23 | 13.3% | 96.7% | 81.1% |
| 2023/24 | 12.5% | 95.3% | 74.5% |
| 2024/25 | 11.7% | 95.3% | 76.5% |
| 2025/26 | 11.9% | 96.5% | 75.8% |

The figures are for centred minutes. Unseen minutes are the least often rated, and their coverage falls in later seasons: promoted squads and players new to the five leagues are linked less often.

### Fitted slopes

xG per 90 per EA overall point above the position-group mean, fitted on the training seasons of each evaluation season at the chosen ridge. Defence is shown as xG prevented (the negative of the defence slope).

| Evaluation season | Centred: attack | Centred: prevented | Starters: attack | Starters: prevented |
| :--- | ---: | ---: | ---: | ---: |
| 2017/18 | 0.0023 | 0.0045 | 0.0020 | 0.0034 |
| 2018/19 | 0.0029 | 0.0044 | 0.0025 | 0.0034 |
| 2019/20 | 0.0028 | 0.0045 | 0.0023 | 0.0036 |
| 2020/21 | 0.0031 | 0.0041 | 0.0025 | 0.0031 |
| 2021/22 | 0.0033 | 0.0041 | 0.0026 | 0.0032 |
| 2022/23 | 0.0033 | 0.0040 | 0.0025 | 0.0030 |
| 2023/24 | 0.0033 | 0.0041 | 0.0025 | 0.0030 |
| 2024/25 | 0.0031 | 0.0041 | 0.0024 | 0.0030 |
| 2025/26 | 0.0029 | 0.0039 | 0.0021 | 0.0029 |

The slopes are stable across folds. A player rated 10 points above his position group is worth about +0.03 xG per 90 in attack and +0.04 prevented (centred), comparable to the larger flat-prior effects in Task 7. The defensive slope is larger than the attacking one in every fold.

### Hindsight ratings: a recorded negative

The first version gave every training row the ratings dated before the **evaluation** season. Those ratings already reflect the training seasons' results, because EA revises ratings after good and bad seasons. In training, the slopes looked two to three times stronger: attack 0.0068–0.0092, prevented 0.0054–0.0091. In evaluation, the prior made predictions worse than team-only: centred −1.83 (1.24), starters −2.85 (1.16). Pooled over the folds, it was worse at every ridge strength. In the 2019/20 fold, for example, the prior's per-row correlation with the residual fell from 0.16 in training to 0.04 in evaluation. Matching each training row to its own season's pre-kickoff ratings fixed this. Any later use of EA ratings as features (Task 8, N3) needs the same time matching. These outputs are kept in `out/player-impact/<lineup>/ea_prior_hindsight/`.

### Limits

- The same replay caveats apply as for Task 7: lineups are given, match sheets are retrospective, and the design (centring, then time matching) was settled on these seasons. The time-matching fix was found by diagnosing the evaluation folds, so the EA results are a replay, not an untouched holdout.
- Identity links are retrospective hypotheses built with all seasons' evidence (Task 6). The ratings themselves respect `available_from`. Using a link before the season it was established assumes that a club knows whom it signed.
- One slope per direction across all positions. Goalkeeper ratings use different attributes, and a per-group slope is untested.
- Positions are taken from the first EA listed position of the vintage used, not from match sheets.

## Reproduce

**Code removed from `main` (24 October 2026).** The experiment was not adopted, so only this report stays. The code is at commit `bb6a1b7`: [`player_impact.py`](https://github.com/hediblk/football-predictions/blob/bb6a1b7/src/standing_prediction/player_impact.py) and [`player_prior.py`](https://github.com/hediblk/football-predictions/blob/bb6a1b7/src/standing_prediction/player_prior.py). Check out that commit to run the commands below.

```bash
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m standing_prediction.player_impact --out-dir out/player-impact
```

This runs all three lineup forms (`--lineup centred starters absolute`) with both priors (`--prior flat ea`). It writes per-fold, per-season, per-league, learning-curve, unseen-player, slope, effect and with-or-without CSVs, row-level predictions and `summary.json` under `out/player-impact/<lineup>/<prior>/`. The EA prior reads compact vintages from `--ea-cache` (default `.cache/players`; in a worktree, pass the main checkout's `/Users/hedibelkahia/codes/football/.cache/players`). The team-only predictions take about 35 seconds and are cached as `out/player-impact/team_only.csv.gz`; `--refit-team` recomputes them. Each lineup form then takes several minutes on one thread, most of it on posterior variances. The run is deterministic (no sampling) and uses only the locked environment (NumPy, pandas, SciPy).
