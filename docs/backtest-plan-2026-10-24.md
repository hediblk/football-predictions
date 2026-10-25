# Backtest plan, 24 October 2026

A betting backtester on the site: pick a universe of matches, write a rule on top of our forecasts, choose a stake rule and a price, and see what the strategy would have won or lost. This plan covers feasibility, data, the rule and staking catalogue, the UI, and eight tasks sized for one agent session and one PR each, in the style of the [feature plan](feature-plan-2026-10-14.md).

Nothing here changes forecasts, `calibrated_weights.json` or the published model. The backtester reads the standalone (no-odds) forecasts the site already publishes; bookmaker prices enter only as the price a bet is struck at and, when a rule asks for it, as a betting condition.

## Verdict

**Feasible, and the data is better than expected.** Five findings, checked on 24 October 2026:

1. **This season's odds already exist for free.** football-data.co.uk's 2026/27 files hold 346 finished matches across the five leagues (to 19–21 October). Each row has 1X2 prices from Bet365, Betfair (sportsbook and exchange), BetVictor, Betway, Paddy Power and Sky Bet, plus the market average and maximum. It also has over/under 2.5 goals and the Asian handicap line with prices. All of these come as pre-closing prices (collected Friday afternoon for weekend games, Tuesday afternoon for midweek) and as closing prices. The files are updated through the season. Pinnacle is missing this season; older seasons have it.
2. **Last season is cheap, not hard.** The calibration dataset already holds walk-forward forecasts for 19,763 matches, 2015/16–2025/26, made at 00:00 UTC on Tuesdays and Fridays from results available then ([miss report](eleven-season-miss-report.md)). Those origins come just before football-data.co.uk collects its pre-closing prices, so every past season pairs cleanly with a price observed after the forecast. The same replay recovers expected goals, so over/under and handicap probabilities can be added.
3. **Our own odds archive can't be bet on as it stands.** `data/odds/` stores de-margined probabilities, not prices. A bet struck at a margin-free price overstates returns by the whole bookmaker margin. Task 2 adds raw prices going forward; the archive is append-only, so the rows before that stay as they are.
4. **The market is the bar, and it is high.** On the 19,763 calibration matches, de-margined average prices score a log loss of 0.9676 against 0.9806 for our no-odds blend. Betting every match on the model's view will lose roughly the margin plus the model's information gap. Any edge will be in particular corners: some leagues, price ranges, or matches where the model and market disagree for a reason. The backtester's job is to find whether such corners exist and to be honest when they don't.
5. **Staking can't create an edge, but it decides what an edge is worth.** Stake size changes variance, drawdowns and the risk of ruin, not the sign of the expected return. Sizing by model probability alone is a trap (see [Staking](#staking)); sizing by edge (Kelly) is the principled version of the idea.

**Noise.** One flat-stake bet at odds of 2.5 has a return standard deviation of about 1.2 stakes. Over 300 bets, ROI carries a standard error of about 7 points, so a +10% season is well within luck. Over 19,763 bets it is under 1 point. Every result shows its bet count and an interval, and this season's numbers are shown as what they are: the only season the calibration never saw, but a small one.

**In-sample caveat.** The saved calibration (`global-4c0170be18f1`) was fitted on 2015/16–2025/26. Team strengths in those replays are walk-forward, but about six global settings were chosen on those same seasons. Results for those seasons are labelled "replayed, in-sample for calibration". Only 2026/27 is an independent holdout.

**Task 1 findings (25 October).** The [feasibility report](backtest-feasibility.md) evaluates all 19,763 matches and 72 strategy/staking/price/timing combinations. All six flat strategies lose at average pre-closing prices; the report recommends Bet365/pre-closing/flat as the named-book reference and no winning preset. Closing prices are absent before 2019/20, so the closing sample is only 12,459 matches at average/maximum prices. Historical quote timing remains approximate. Task 2 adds sibling raw-price files without rewriting the existing archive; one live domestic combined-market request confirmed a two-credit charge.

## Odds sources

| Source | What it has | Cost and terms | Use |
| --- | --- | --- | --- |
| [football-data.co.uk](https://www.football-data.co.uk/data.php) | 1X2 from 6+ books, market average and maximum, Betfair exchange; pre-closing and closing; O/U 2.5; Asian handicap; five leagues back to the 1990s, Pinnacle in older seasons | Free, "intended for private individuals only", not commercial or automated AI products | Primary source, subject to D1 |
| Our archive (The Odds API, `eu`) | Daily 1X2 since 13 Oct 2026 with true observation timestamps, plus the Champions League, Europa League and Conference League | 1 credit per competition per day; 500 a month free | Add raw prices (Task 2); later the paper-trading record (Task 8) |
| The Odds API historical endpoint | Snapshots back to 2020 | Paid plans only | No |
| [Betfair historical data](https://historicdata.betfair.com/) (Basic) | Exchange prices by minute with true timestamps | Free with a Betfair account, personal use | Later, if price timing becomes the question; the user would need to create the account |
| Kaggle odds datasets | Mostly mirrors of football-data.co.uk or scraped OddsPortal | Free, unclear provenance and licence | No added value |
| OddsPortal, Flashscore | Many books and markets | Scraping is against their terms | No |

No free source with acceptable terms gives both-teams-to-score, correct-score or double-chance prices for these leagues. Double chance and draw-no-bet could be priced synthetically from 1X2, but a synthetic price isn't one a bettor could get; leave them out. The Champions League has no free historical prices before our archive (13 October 2026), and the Champions League model already uses archived prices (Plan E), so its forecasts aren't independent of the market. Keep the backtester to the five leagues.

**Timing.** A bet must be struck at a price observed after the forecast it relies on, and before kickoff.

- **Past seasons and this season (replayed):** forecast at 00:00 UTC Tuesday or Friday, bet at the pre-closing price collected that afternoon, or at the closing price. Both are clean.
- **This season (published receipts):** saved at about 05:30 UTC on match day since 14–17 October, so only the closing price comes after them.
- **Rule:** closing prices are never a betting signal for an earlier bet. Closing-line value (did our price beat the close?) is reported as a check, since it is the best early sign of a real edge.

## Strategy model

A strategy is a JSON object. The URL hash carries it, so any backtest is a shareable link. The engine and the UI both code against this shape, which lets Tasks 4 and 5 run in parallel:

```json
{
  "v": 1,
  "universe": {"comps": ["PL", "PD"], "seasons": [2025, 2026], "include": [], "exclude": [64],
               "venue": "any", "matchdays": [1, 38], "forecast": "replayed"},
  "market": "1x2",
  "rule": {"pick": "edge", "conditions": [{"field": "edge", "op": ">=", "value": 0.05},
                                          {"field": "price", "op": "between", "value": [1.8, 4.0]}]},
  "stake": {"method": "kelly", "fraction": 0.25, "cap": 0.03, "base": "start_of_day"},
  "execution": {"book": "avg", "timing": "pre", "commission": 0},
  "bankroll": 100
}
```

### Universe

- **Competitions:** any of the five leagues.
- **Seasons:** 2026/27 (out of sample) and 2015/16–2025/26 (replayed, in-sample for calibration).
- **Teams:** include only, or exclude, by football-data.org id. Optionally only when the team plays at home or away. A team filter means "matches involving the team"; a separate option restricts bets to that team's side.
- **Slice:** matchday range, months, weekday or midweek.
- **Forecast kind:** replayed (every season, uniform timing) or published receipts (this season, from mid-October, closing price only).

### Markets

| Market | Model probability | Prices | When |
| --- | --- | --- | --- |
| 1X2 (home, draw, away) | Blended `p` | Every book, pre-closing and closing | Task 3 |
| Over/under 2.5 goals | `o25` from the blended scoreline distribution | Bet365, average, maximum, Betfair exchange | Task 6 |
| Asian handicap (main line) | From the scoreline distribution, with quarter lines split into two half-stakes | Bet365, average, maximum, Betfair exchange | Task 6 |

### Selection rules

A rule picks at most one selection per match and market, then applies its conditions (all must hold).

| Pick | Bets on | Notes |
| --- | --- | --- |
| Model favourite | The outcome with the highest model probability | The user's "who's winning" rule |
| Specific outcome | Home, draw or away; over or under | For example "back the draw" |
| Best edge | The outcome with the largest `p × price − 1` | Value betting |
| Market favourite | The shortest price | A baseline that loses about the margin |
| Disagreement | The model's favourite when it differs from the market's | Where the model claims to know something |

| Condition field | Meaning |
| --- | --- |
| `p` | Model probability of the selection |
| `edge` | Expected return at the chosen price: `p × price − 1` |
| `gap` | Model minus de-margined market probability, in points |
| `price` | Decimal price at the chosen book and timing |
| `xg_diff` | Pre-match expected goals, selection side minus opponent |
| `xg_total` | Pre-match expected total goals (for over/under) |
| `elo_agrees` | The Elo component picks the same outcome |
| `rating_gap` | Club strength rating difference |
| `stakes` | The match carries a title, top-four or relegation Stakes tag |

### Staking

| Method | Stake | Notes |
| --- | --- | --- |
| Flat | 1 unit per bet | The reference; ROI is easy to read |
| Fixed fraction | x% of current bankroll | Compounds |
| By probability | base × p ÷ 0.5, or user-set probability bands | The user's idea; shown with the warning below |
| By edge | base × edge ÷ 0.05 | Bigger stakes where the price is wrong by more |
| Kelly | `(p × price − 1) ÷ (price − 1)` of bankroll, times ¼, ½ or 1, with a per-bet cap | No bet when the edge is ≤ 0 |
| To win | Stake so every winner returns the same profit | Puts more on favourites |

**Why probability alone is a trap.** A 65% favourite at 1.40 is priced at 71%: at that price every unit staked expects to lose 9 points (0.65 × 1.40 − 1), however confident the model is. A 35% outsider at 3.40 is priced at 29% and expects +19 points per unit. Full Kelly puts 7.9% of the bankroll on the outsider and nothing on the favourite. Confidence matters only relative to the price. This is value betting, not arbitrage: arbitrage covers every outcome across books for a sure profit, needs no model, and in snapshot data like this mostly reflects stale prices.

**Trust in the model.** Kelly on an overconfident model overbets. An optional "trust" slider stakes on `w × p_model + (1 − w) × p_market` instead of `p_model`, the usual practical correction. It is labelled as using market information in the betting rule; the forecast itself stays standalone.

**Same-day bets.** Stakes on the same day are sized from the bankroll at the start of that day, with an optional cap on total daily exposure, so simultaneous bets don't size off results not yet known.

### Execution

- **Book:** Bet365, market average, best price (maximum across books, flattering since no one gets every best price), Betfair exchange with a commission setting (default 2%).
- **Timing:** pre-closing or closing.
- **Settlement:** 90-minute results; Asian handicap pushes and half-wins; void when a price is missing, counted in the coverage line.

### Results

- **Hero:** ROI at poster scale (amber, red when negative), with bets and staked beside it.
- **Bankroll line:** amber strategy line, dashed ink for the market-favourite baseline on the same universe, a dim zero line.
- **Summary board:** bets, staked, profit, ROI with a 95% interval (bootstrap by matchday, fixed seed), strike rate against the strike rate the prices imply, average price, maximum drawdown, longest losing run, closing-line value.
- **Breakdowns:** by season, league, team, price band and month. A strategy that lives on one season or one club shows it.
- **Bet log:** ruled board with date, match, selection, price, model probability, edge, stake, result and running bankroll; rows link to `#match/<comp>/<id>`.
- **Coverage line:** matches in the universe, with a price, bet on, and voids.
- **Labels:** forecast kind and the in-sample caveat for replayed seasons; "Historical simulation, not betting advice."

## UI

**A fifth section tab, Backtest** (D2), after Clubs. It is a tool rather than a frame, so the feature plan's "no new tab" rule doesn't fit it. It follows `DESIGN.md`: legend-cut frames, ruled boards, chips and chip-selects, no new hues, and no motion beyond what exists.

```
Backtest
┌ Strategy ───────────────────────────────────────────────┐
│ Presets: [Model's pick] [Value ≥5%] [¼ Kelly] [Fade fav] │
│ Universe  [PL][PD][BL1][SA][FL1]  Seasons [25/26][26/27]  │
│           Teams: + include / − exclude   Home/away: any   │
│ Rule      Pick [Best edge ▾]  edge ≥ [5%]  price [1.8–4.0]│
│ Stake     [Flat][Fraction][By p][By edge][Kelly ¼][To win]│
│ Price     Book [Average ▾]  Timing [Pre-closing][Closing] │
└──────────────────────────────────────────────────────────┘
┌ Result ─────────────────────────────────────────────────┐
│  −3.8%   ROI · 412 bets · 412 staked · 95% −11.0 to +3.4 │
│  [bankroll line, dashed baseline]                         │
│  Summary board · breakdowns (season, league, price band)  │
└──────────────────────────────────────────────────────────┘
┌ Bets ───────────────────────────────────────────────────┐
│ ruled board, expandable rows, link to the match page      │
└──────────────────────────────────────────────────────────┘
```

The engine runs in the browser over 20,000 rows at most, so results update as controls change, with no server. On phones the frames stack, the strategy frame collapses to a one-line summary once run, and the bet log scrolls inside its frame. Club pages could later link to "Backtest this club"; that's left out of this plan.

**Data.** One file per season, `site/data/backtest/<season>.json`, columnar, loaded only when the tab opens: about 1,800 matches with forecast, result and prices, around 300 KB raw and 70 KB compressed per season. The current season's file is rebuilt in the daily refresh; past seasons are built once and rebuilt only when the calibration changes.

## Decisions for the user

| | Decision | Options | Recommendation |
| --- | --- | --- | --- |
| D1 | Publishing football-data.co.uk prices on the public site | (a) Ask the owner for permission, with credit; (b) keep historical-price backtests local (`out/`, CLI) and publish only our own archive's prices; (c) publish without asking | (a). Build in `out/` until there's an answer. Mention that our refresh downloads the CSVs automatically, since the terms single out automated use. |
| D2 | Where it lives | New Backtest tab; a frame inside Model | New tab |
| D3 | Paper trading upcoming fixtures (Task 8) | Yes; no | Decide after Task 1. It is the only true forward test, but it publishes picks, which reads as tipping. |
| D4 | Seasons offered | 2026/27 only; plus 2025/26; all eleven | All eleven, labelled in-sample, with 2026/27 marked as the holdout |

## Rules for every task

Read `AGENTS.md`, `DESIGN.md`, the [site data contract](site-data-contract.md), both ADRs and the feature plan's [rules for every task](feature-plan-2026-10-14.md#rules-for-every-task) (exporter, contract, checks, CSS blocks and conflict avoidance all apply). In addition:

- **No leakage.** A bet's price is observed after its forecast and before kickoff. Closing prices are never a condition for a pre-closing bet. Results, xG and later identities never reach a forecast.
- **Standalone forecasts only.** Bet signals use the published no-odds model. Market information may appear in a betting rule (edge, gap, trust) and is labelled there; it never changes the forecast.
- **Every ROI has a count and an interval.** No preset is chosen or described as winning on in-sample results without saying so.
- **Fixed seeds** for bootstrap intervals; the same seed in Python and JavaScript summaries.
- **Coverage.** Report matches without prices, failed identity joins and voids; never drop them silently.
- **Immutable observations.** Archived odds and receipts are never rewritten; new price columns are added going forward.

## Overview

| Task | Wave | Depends on | Size | Suggested agent | Status |
| --- | --- | --- | --- | --- | --- |
| 1. Feasibility study | A | none | M | Codex | [PR #76](https://github.com/hediblk/football-predictions/pull/76) |
| 2. Raw prices in the odds archive | A | none | S | Claude | [PR #75](https://github.com/hediblk/football-predictions/pull/75) |
| 3. Backtest data, 1X2 | A | 1 for parity summaries; publishing waits for D1 | L | Codex | Pending |
| 4. Backtest engine | A | this plan's strategy shape | L | Claude | Pending |
| 5. Backtest view | B | 3, 4 | L | Claude | Pending |
| 6. Over/under and Asian handicap | C | 3, 4, 5 | M | Codex | Pending |
| 7. Robustness and comparison | C | 5 | M | Claude | Pending |
| 8. Paper trading | D | 2, 5, D3 | M | Codex | Pending |

Wave A's four tasks touch separate files and can run at once. Task 4 codes against a small fixture in the documented shape until Task 3 lands.

## Tasks

### 1. Feasibility study

Offline, before any UI. Join the calibration dataset's 2015/16–2025/26 forecasts (production blend: `dc_0.75x1.3` and Elo at 0.844/0.156) with football-data.co.uk prices. Then score six baselines with flat and quarter-Kelly stakes: market favourite, model favourite, best edge ≥ 0, ≥ 5% and ≥ 10%, and disagreement. Report ROI with matchday-clustered intervals, closing-line value, and splits by season, league and price band, at average, best and Bet365 prices, pre-closing and closing. Check identity joins and coverage.

- **Output:** `docs/backtest-feasibility.md` and a small Python reference (`packages/forecast-calibration`) that computes the same summaries; Task 3 uses it to produce parity numbers.
- **Decides:** default book and timing, which presets ship, and whether the copy should open with "the model doesn't beat the market" if that's what the numbers say.

### 2. Raw prices in the odds archive

`scripts/archive_odds.py` keeps writing the existing columns and adds raw decimal prices: market average, best price and Pinnacle 1X2. It also fetches the totals market (2.5 line) for the five leagues. Add columns going forward, or write a sibling `<code>_prices.csv` if appending columns would break readers; check `match_odds` and every reader. Totals cost about 150 more credits a month (about 390 of 500 in all); confirm against the API's usage headers. Update `data/odds/README.md`.

### 3. Backtest data, 1X2

`scripts/build_backtest_data.py` writes one columnar file per season with fixture identity (football-data.org ids where they exist, for match-page links), kickoff, result, Understat xG, forecast kind and origin, `p`, Elo, expected goals, Stakes flag, and 1X2 prices per book, pre-closing and closing.

- **Past seasons** come from the calibration features.
- **2026/27** is replayed at the same Tuesday/Friday origins, so every season follows one timing rule; published receipts are added as a second forecast kind.
- **Identities:** football-data.co.uk names are joined with `normalize_team`, and unmatched rows are listed.
- **Contract:** schema mapping, validator checks and a contract row.
- **Refresh:** a non-blocking step in `scripts/refresh_site.sh`; a failure keeps the previous file and its timestamp.
- **Docs:** ADR 0003 for in-browser backtests over a published per-match price file, recording D1.
- **Until D1 is settled:** it writes to `out/backtest/`, with a flag to publish.

### 4. Backtest engine

`site/assets/backtest-engine.js`: pure functions, no DOM. Covers universe filtering, selection and conditions, staking (all six methods, caps, start-of-day sizing, trust blend), settlement (commission, voids), the bankroll path, metrics, the seeded matchday bootstrap and breakdowns. It also encodes and decodes the strategy to the URL hash. Each season file carries Python-computed summaries for the presets, and `scripts/check_site.py` asserts the engine reproduces them, which gives JS/Python parity without a JS test framework.

### 5. Backtest view

The Backtest tab: strategy frame with presets and chips, result hero, bankroll chart with a text-equivalent table, summary board, breakdowns, bet log linking to match pages, coverage and labels, URL state, phone layout. Update `DESIGN.md` for the new components and add the route and selectors to `routes()` in `check_site.py`.

### 6. Over/under and Asian handicap

Extend the replay (the miss report already recovers the blended scoreline distribution) to export `o25` and main-line handicap probabilities for every season. Add totals and handicap prices to the data, quarter-line settlement to the engine, and a market chip to the view. Coverage per market is stated.

### 7. Robustness and comparison

- **Per-season and holdout:** results per season, with 2026/27 shown apart as the holdout.
- **Overfitting warning:** an "edge found in-sample" note when a strategy is positive only in calibration seasons; a count of the strategies tried this session.
- **Comparison:** two strategies on one chart.
- **Saved strategies:** in `localStorage`, as a per-viewer convenience.

### 8. Paper trading (if D3 is yes)

Each refresh applies saved public presets to the next round's fixtures, at prices just archived with raw prices (Task 2). It freezes the bets as receipts, like forecast receipts: never edited, settled after the result. The record builds a true out-of-sample track record from the day it starts.
