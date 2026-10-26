# Betting backtest feasibility, 25 October 2026

Task 1 of the [Backtest plan](backtest-plan-2026-10-24.md). This is an offline historical-price study. Forecasts, calibration, published data and archived observations are unchanged.

**The model does not beat the market in these broad strategies.** At average pre-closing prices, all six flat-stake strategies lose, and every 95% interval is below zero. The model favourite returns −3.90%; selecting the largest model edge when it is at least 5% returns −10.85%. Quarter-Kelly does not repair the losses. Positive results appear in some maximum-price benchmarks and individual seasons; neither establishes an executable edge.

## Data and coverage

- **Forecasts:** 19,763 matches, E0/SP1/D1/I1/F1, 2015/16–2025/26; all 55 league-season CSVs were available offline. All forecast fixtures joined one-to-one with normalized home/away identities; zero unmatched rows, date mismatches or result mismatches.
- **Model:** saved calibration `global-4c0170be18f1`, xG weight 0.75, scale 1.3, main/Elo shares 0.8441680232595445/0.15583197674045546. The forecast is the existing log-space blend without odds; this study never fits a setting.
- **Dataset SHA-256:** `889897330dcf19f48977a06ba62895c4b599027a89b444a91aee747c51a7a127`. Source CSV content hashes, artifact/code hashes and runtime versions are in `out/backtest-feasibility/provenance.json`.
- **Calibration in-sample:** team strengths were fitted walk-forward, but the global weights were selected on these eleven seasons. These are not independent betting holdouts. No 2026/27 forecasts were rebuilt in this task; that replay belongs to Task 3.

| Price source | Timing | Priced fixtures | Without a complete price |
| --- | --- | --- | --- |
| average | close | 12,459 | 7,304 |
| average | pre | 19,762 | 1 |
| best | close | 12,459 | 7,304 |
| best | pre | 19,762 | 1 |
| bet365 | close | 12,458 | 7,305 |
| bet365 | pre | 19,757 | 6 |

Closing prices do not exist in the cached 2015/16–2018/19 files. The closing sample therefore starts in 2019/20 and has 12,459 fixtures for average/maximum prices, 12,458 for Bet365. Missing quotes remain exclusions: there is no substitution of pre-closing prices for a missing close, or one bookmaker for another. Every selection needs a complete finite 1X2 triple above 1. Legacy `BbAv`/`BbMx` columns supply average/maximum prices before the `Avg`/`Max` schema.

## Protocol

**Prices and timing.** The provider identifies the ordinary columns as pre-closing and the `C` columns as closing ([column definitions](https://www.football-data.co.uk/notes.txt)). Tuesday/Friday afternoon collection is the existing calibration's approximate historical timing convention. CSVs do not timestamp individual quotes. Forecast origins precede kickoff and training availability does not exceed the origin. Older CSVs lack kickoff times; their saved forecasts retain the existing noon-UTC anchor. The study verifies identity, calendar date and that same anchor, rather than claiming a verified historical betting timestamp. Revisions, early kickoffs and later fixture announcements cannot be reconstructed exactly.

**Selection.** Six rules were fixed before calculating returns. Market favourite is the shortest price in the chosen price set; model favourite is the largest no-odds forecast probability; best edge maximizes `p × decimal_price − 1` and applies the stated inclusive threshold; disagreement backs the model favourite only when it differs from the market favourite. Ties resolve home, draw, away. Each rule makes at most one selection per match. Closing runs select at the close; no closing price enters a pre-closing decision.

**Staking and settlement.** Flat means one unit per selected bet, a unit-return benchmark without a finite-bankroll constraint. Quarter-Kelly uses `0.25 × max(p × price − 1, 0)/(price − 1)`, capped at 3% per bet. Each season starts with 100 units shared across the five leagues. All pre-closing bets from a Tuesday/Friday origin use the same starting bankroll, so Saturday results cannot resize Sunday's already-priced bets. Closing bets use the bankroll at the start of their UTC match day. If requested exposure exceeds 100%, all stakes in that batch scale proportionally. The reference rejects overlapping unsettled batches rather than borrowing future proceeds. Wins profit `stake × (price − 1)`, losses lose the stake; 90-minute results and zero sportsbook commission. Kelly rejects nonpositive edges, so its bet counts can be lower than flat's.

**Intervals.** ROI is total profit divided by total staked, weighted by stake rather than equally by league-season. Each 95% percentile interval uses 2,000 bootstrap draws of UTC match dates, keeping all five leagues on a date together; seed 7. The bootstrap conditions on realized selections and stakes. It does not rerun the path-dependent Kelly policy under reordered outcomes, refit calibration or account for searching many strategies. Mulberry32, row-major random draws and linear percentile interpolation are specified in the reference for future Python/JavaScript parity. Breakdowns allocate the original portfolio's bets and stakes; they do not independently resize each subgroup. Drawdown is the largest within-season fall in cumulative daily profit, in units; losing runs follow kickoff order and reset by season. Simultaneous fixtures break ties by league code, then home name; losing-run lengths are sequence statistics, especially where old kickoffs use a noon anchor.

**Execution limits.** Market averages are comparison prices, not an individual bookmaker offer. Maximum prices are an optimistic best-of-books benchmark without proof that every price was simultaneously available or obtainable. Bet365 is the single-book reference. No account limits, slippage, rejected bets or taxes are modeled.

## Six baselines at average pre-closing prices

Each cell gives ROI, its 95% interval and bet count. Counts differ when Kelly skips a nonpositive edge.

| Selection | Flat | Quarter-Kelly |
| --- | --- | --- |
| Market favourite | -2.67% [-3.89, -1.35]; n=19,762 | -5.00% [-8.17, -1.78]; n=5,422 |
| Model favourite | -3.90% [-5.14, -2.55]; n=19,762 | -8.05% [-11.53, -4.72]; n=7,063 |
| Best edge ≥0% | -9.67% [-12.36, -6.90]; n=15,970 | -9.61% [-13.56, -5.61]; n=15,970 |
| Best edge ≥5% | -10.85% [-14.52, -7.21]; n=10,657 | -10.11% [-14.44, -5.64]; n=10,657 |
| Best edge ≥10% | -10.11% [-14.88, -5.38]; n=7,169 | -11.33% [-16.59, -6.00]; n=7,169 |
| Disagreement | -16.72% [-22.93, -10.25]; n=1,739 | -16.04% [-24.39, -7.67]; n=1,641 |

## Price-source sensitivity

Flat stakes. Closing rows cover only the later seven seasons, so they cannot be interpreted as a matched before/after timing experiment on the full eleven-season sample. The CSV outputs allow that common-fixture comparison.

| Price source | Timing | Model favourite | Best edge ≥5% |
| --- | --- | --- | --- |
| average | close | -3.20% [-4.87, -1.56]; n=12,459 | -9.11% [-13.33, -4.76]; n=7,504 |
| average | pre | -3.90% [-5.14, -2.55]; n=19,762 | -10.85% [-14.52, -7.21]; n=10,657 |
| best | close | +0.85% [-0.88, +2.55]; n=12,459 | -0.54% [-4.43, +3.36]; n=10,733 |
| best | pre | -0.41% [-1.70, +1.01]; n=19,762 | -3.36% [-6.31, -0.21]; n=15,943 |
| bet365 | close | -4.26% [-5.88, -2.61]; n=12,458 | -10.04% [-14.41, -5.69]; n=7,168 |
| bet365 | pre | -4.53% [-5.78, -3.18]; n=19,757 | -8.57% [-12.41, -4.88]; n=10,936 |

The complete `summaries.csv` contains all 72 combinations: six selections × two staking rules × three price sources × two timings, including the market-favourite baseline at maximum prices. Some maximum-price benchmarks are positive; that is evidence about the price benchmark, not a demonstrated model edge at a named bookmaker.

## Season, league and price-band checks

Average pre-closing prices and flat stakes. These tables show the model favourite and the 5% edge preset; `breakdowns.csv` includes all six selections, both staking rules and all price/timing choices, with counts and intervals for each subgroup. An attractive individual season or subgroup was not used to choose a new rule.

| Season | Model favourite | Best edge ≥5% |
| --- | --- | --- |
| 2015/16 | -7.78% [-12.35, -3.07]; n=1,826 | -15.78% [-26.79, -4.70]; n=1,045 |
| 2016/17 | -0.64% [-4.71, +3.41]; n=1,826 | -16.74% [-27.48, -5.93]; n=951 |
| 2017/18 | -4.52% [-8.80, -0.32]; n=1,826 | -15.54% [-26.14, -4.02]; n=1,026 |
| 2018/19 | -7.22% [-11.25, -2.98]; n=1,826 | -11.43% [-22.68, +0.66]; n=1,075 |
| 2019/20 | -0.87% [-4.96, +3.15]; n=1,725 | +8.65% [-6.58, +25.04]; n=1,021 |
| 2020/21 | -4.71% [-9.03, +0.10]; n=1,826 | +3.85% [-9.57, +18.95]; n=960 |
| 2021/22 | -5.37% [-9.18, -1.66]; n=1,825 | -9.01% [-20.29, +3.06]; n=948 |
| 2022/23 | -2.27% [-6.73, +2.21]; n=1,826 | -6.93% [-18.35, +5.24]; n=959 |
| 2023/24 | -1.85% [-6.26, +2.77]; n=1,752 | -25.83% [-36.46, -15.31]; n=898 |
| 2024/25 | -3.28% [-7.49, +1.31]; n=1,752 | -13.23% [-24.35, -2.59]; n=887 |
| 2025/26 | -4.09% [-8.50, +0.24]; n=1,752 | -19.66% [-30.07, -9.14]; n=887 |

| League | Model favourite | Best edge ≥5% |
| --- | --- | --- |
| D1 | -7.48% [-10.69, -4.16]; n=3,366 | -9.60% [-18.36, +0.25]; n=1,669 |
| E0 | -3.22% [-6.12, -0.28]; n=4,180 | -2.10% [-10.07, +6.19]; n=2,536 |
| F1 | -4.21% [-7.23, -1.08]; n=3,857 | -12.35% [-20.31, -3.75]; n=1,939 |
| I1 | -2.91% [-5.73, +0.03]; n=4,179 | -19.27% [-26.18, -11.88]; n=2,221 |
| SP1 | -2.39% [-5.35, +0.50]; n=4,180 | -12.02% [-19.62, -4.03]; n=2,292 |

| Decimal price | Model favourite | Best edge ≥5% |
| --- | --- | --- |
| 1-1.5 | -0.50% [-2.39, +1.31]; n=4,105 | +7.67% [-0.47, +15.85]; n=190 |
| 1.5-2 | -2.74% [-4.72, -0.68]; n=6,774 | -9.03% [-15.20, -2.89]; n=823 |
| 2-3 | -5.81% [-8.30, -3.19]; n=8,257 | -10.64% [-15.09, -6.39]; n=2,599 |
| 3-5 | -14.39% [-25.16, -2.54]; n=614 | -13.29% [-18.47, -8.00]; n=3,649 |
| 5+ | +35.67% [-100.00, +175.25]; n=12 | -9.88% [-18.56, -1.05]; n=3,396 |

## Closing-line value

For covered pre-closing bets, CLV is the unweighted mean `entry_price / closing_price − 1` for the same selected outcome. Positive means the entry price was better. Closing-price strategies have no later comparison, so CLV is unavailable. Average-to-average and maximum-to-maximum comparisons do not establish same-book execution.

| Selection, flat stakes | Bets with a close | Mean CLV |
| --- | --- | --- |
| Market favourite | 12,458 | -0.056% |
| Model favourite | 12,458 | -0.053% |
| Best edge ≥0% | 10,012 | +0.019% |
| Best edge ≥5% | 6,560 | +0.100% |
| Best edge ≥10% | 4,328 | +0.422% |
| Disagreement | 1,056 | -0.588% |

A positive CLV in a small or selected slice is not a replacement for realized return uncertainty. Closing prices are only a diagnostic for pre-closing bets.

## Decisions for the first page

- **Default:** Bet365, pre-closing, flat stake, model favourite. This uses a named bookmaker and makes the simplest strategy visible; it is not selected for a profitable result.
- **Presets:** model favourite; market favourite as the comparison baseline; best edge ≥5%; and quarter-Kelly on the same ≥5% selection as a staking demonstration. Keep the other evaluated rules available as explicit choices, without calling any a winning strategy.
- **Opening copy:** “The model does not beat the market in these historical baseline strategies.” Show count, interval and calibration in-sample label beside the result.
- **Publishing:** D1 was resolved on 26 October 2026 when the user confirmed publication permission; [ADR 0004](adr/0004-backtest-deployment-switch.md) removes the original output restrictions. No UI, paper trading or automatic betting was implemented by this study.

## Reproduce and reuse

From the repository root with the existing installed packages and provider caches:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv/bin/python -m forecast_calibration.backtest_feasibility \
  --out-dir out/backtest-feasibility --bootstrap 2000 --seed 7
```

The command is offline and fails on a missing source cache or a changed dataset hash. Outputs default to this repository's `out/` directory; `--out-dir` can select another destination. No provider key or model refit is needed.

- `matches.csv`: matched no-odds forecasts, results and raw 1X2 prices, for Task 3.
- `coverage.csv`, `unmatched.csv`: every league-season/price/timing denominator and identity exclusion.
- `summaries.csv`, `breakdowns.csv`: all strategy results and subgroup uncertainty.
- `bets.csv`: average/pre-closing bets under all six rules and both stake rules, including selected probabilities, prices, stakes and profit.
- `parity.json`: twelve average/pre-closing preset summaries for the browser engine to reproduce.
- `provenance.json`: input/output hashes, seed, bootstrap, staking and runtime configuration.

The reusable functions are `select_bets`, `stake_bets`, `summarize` and `bootstrap_indices` in `forecast_calibration.backtest_feasibility`. Existing offline tests pass (124); hand-calculated settlement, batch sizing, exposure caps, production-blend equality, closing-price isolation and deterministic bootstrap checks also pass. The portable random indices were checked against JavaScript's Mulberry32 arithmetic. These checks establish the reference calculation, not a prospective betting edge.
