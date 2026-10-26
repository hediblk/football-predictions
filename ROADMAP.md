# Roadmap

The goals are good league-winner odds and good Champions League forecasts, from single matches through to the trophy. Title outcomes are too few to tell models apart (50 league-seasons put a standard error of 0.01–0.03 on champion log loss). Model changes are therefore judged on match log loss over all seasons, with the top-three points bias, title metrics and the market as checks. [PLAN.md](PLAN.md) records what is implemented and why.

Recently done: the calibrated xG scale and ridge 2 (Plan C), filling results football-data.org lags on from Understat, the daily [odds archive](data/odds/README.md), Champions League league offsets with one European club scale (Plan D), league levels set by archived Champions League prices (Plan E), and past-date league reruns (`football-predict --as-of`) with dated site history in `site/data/history`, backfilled for 2026/27 and extended by every refresh, which feeds the title-race charts on each competition page, what's at stake for the next round's games (Matches and club pages; Champions League top eight, top 24 and trophy too) and the Clubs tab's weekly power ranking with movement arrows, which now includes the Champions League clubs from outside the five leagues. League club pages also describe how each club plays (strengths, weaknesses, style, run-in, form and game state) from the last 38 league games' shots and match stats, in the manner of WhoScored's characteristics and SoccerSTATS' run-in and late-goal tables.

The site/model boundary is also checked: offline numerical regressions, exporter tests, a published-data contract, and validation of the exact revision deployed. The model and site keep their existing folders and separate CI workflows. See [ADR 0001](docs/adr/0001-site-model-boundary.md). Every view is also loaded in headless Chromium on site pull requests and before each deploy, and deployed asset URLs carry a content version so browsers never mix cached code with new files ([ADR 0002](docs/adr/0002-site-browser-checks.md)).

The [football feature research (14 October 2026)](docs/football-feature-research-2026-10-14.md) compares established stats and prediction sites and their social formats, with 36 feature ideas and their data requirements. Recommended starting points are dedicated post-match reports, round race movers, shareable cards, rolling xG and points-versus-pre-match-expectation charts. Shot maps and xG timelines depend on individual-shot data. The [feature plan (14 October 2026)](docs/feature-plan-2026-10-14.md) splits the match page (pre-game, post-game, shots, box scores and Champions League running data), the scorecard, race movers, rating history, games that matter and who's beating the model into fourteen tasks, each sized for one agent session and one PR.

## Next

### 1. Champions League league offsets: follow-ups

The main fix is done (Plan D in [PLAN.md](PLAN.md)). League offsets now shrink toward a typical league level instead of the Premier League, and each club gets a shrunk European effect. Replay log loss fell from 0.9395 to about 0.909. Left to do:

- **Recheck the market weight after MD6.** Archived Champions League prices now set each league's current level (Plan E), which cut the Premier League's lead over La Liga and the Bundesliga by about 40% and put La Liga above Ligue 1. The weight (10 per quote) and shift ridge (5) rest on one matchday of prices; refit them by leave-one-out on prices and score them on results once six matchdays are archived.
- **Serie A looks low.** It sits last of the big five (57.5 against StatsUltra's 69.8); its few priced fixtures barely move it.
- **Europa and Conference League data.** These are where mid-table clubs meet across leagues, so they matter for league levels. football-data.org's free tier refuses the Europa League (paid plans only) and has no Conference League; openfootball stops at 2024/25 plus qualifiers. The Odds API quotes both, and the archive has saved their 1X2 prices since 13 October 2026 (about 36 fixtures per round; 17 of the first 36 involve two clubs the Champions League model rates). Finished [results come from ESPN for 2025/26 onward](data/results/README.md), backfilled and appended daily without a key; The Odds API scores endpoint is no longer needed. [Model plan Task A](docs/model-plan-2026-10-16.md) adds `--european-history both` to use the covered 90-minute results alongside openfootball. The [three-variant replay](docs/el-ecl-history-evaluation.md) records the integration decision, exclusions and league offsets; the archived prices stay for the 10 December recheck.

### 2. Scorecard in Matches and Model

The Matches scorecard and Model Track record frame show log loss, RPS and Brier against each competition’s prior five-season outcome frequencies and Elo, with calibration counts and cumulative weekly scores. Published receipts and reconstructed forecasts are reported separately and together. The market comparison (feature-plan Task 14) remains pending until at least 300 published domestic fixtures have eligible archived quotes. Champions League forecasts already use earlier archived prices (Plan E), so they are not independent of the market there.

The [miss-analysis and recap-card plan](docs/evaluation-plan-2026-10-17.md) adds how forecasts go wrong to the scorecard: called against actual outcomes, draws against upsets, and whether the favourite won on xG. An eleven-season report runs first; match, round and race cards come alongside it.

### 3. Players (phase 6): site feature done, forecasting closed

Every club page has a **Squad** subtab built from EA SPORTS FC ratings and match sheets: ideal and most-used XIs, playing time, xG and xA per 90, and XI history, refreshed daily. See the [squads and players plan](docs/xi-ui-plan-2026-10-15.md) and [squad matching](docs/squad-matching.md). Understat lineups since 2014/15 and dated EA rating vintages are archived under `data/players/`.

Player data does not improve forecasts. A pooled xG plus-minus model finds a small, real xG gain from lineups measured against each team's usual lineup ([Task 7 and 7b](docs/player-impact-xg-plus-minus.md)). In match probabilities, an expected-XI adjustment fails on held-out seasons with either prior, and even the actual starters leave log loss unchanged within noise ([Task 8](docs/expected-xi-forecast-adjustment.md), [EA follow-up](docs/expected-xi-ea-prior-comparison.md)). Forecasts stay team-level. An injuries source (N1) remains a possible display-only addition to the Squad tab.

### 4. Backtest

Task 5 adds the Backtest page over the data exporter and browser engine, with local historical-price previews and synthetic browser checks. Public prices remain unavailable pending D1; additional markets, comparison/saving and paper trading remain Tasks 6–8.

A Backtest tab where a strategy is a universe (leagues, seasons, teams), a rule on our standalone forecasts (model pick, edge, probability, expected goals, Stakes), a stake rule (flat, fraction, by probability or edge, Kelly) and a price (book, pre-closing or closing). It reports profit, ROI with an interval, drawdowns and closing-line value. football-data.co.uk already has this season's 1X2, over/under and handicap prices, and the calibration replays cover 2015/16–2025/26 (in-sample for calibration; 2026/27 is the holdout). The market's log loss is 0.013 lower than our no-odds blend's, so broad strategies are expected to lose. The [backtest plan (24 October 2026)](docs/backtest-plan-2026-10-24.md) has the data checks, the rule and staking catalogue, the UI, four open decisions (including permission to publish the prices) and eight tasks.

## Parked

- **Repository rename:** deferred. GitHub redirects remotes but not the Pages address; preserve existing links or set up a custom domain before renaming.
- **Elo K and season regression:** at most 0.0005 log loss in the Plan C search.
- **Non-penalty xG:** tested in [model plan Task B](docs/npxg-penalty-rate.md). npxG strengths plus a shrunk team penalty rate gain 0.0006 held-out log loss (standard error 0.0004), at the 0.0005 yardstick but within noise; npxG alone gains 0.0005 (0.0005). Worth including only if the calibration is rebuilt for another reason.
- **Promoted teams and preseason priors:** second divisions (E1, SP2, D2, I2, F2) with a division offset. This matters for early-season tables, not title races.
- **Dynamic, score-driven team strengths:** would replace both time decay and Elo, a bigger change.
- **Strength uncertainty in season simulations:** tested and rejected. Title favorites already win as often as forecast, and added noise made title forecasts worse. Revisit only for points ranges or the Champions League offsets.
- **Player-level forecasts:** closed after Task 8. Confirmed-XI forecasts (N2) and boosting on lineup features (N3) are parked unless a new information source (injury news, long absences) shows a measurable gain.
- **Research backlog:** model ideas from the forecasting literature, each with its source, protocol, effort and pitfalls, are in the [research backlog (24 October 2026)](docs/research-backlog-2026-10-24.md). R1/R2 (free market pool, margin removal) and R3 ([late-season stakes](docs/late-season-stakes.md)) are tested and not adopted. Still open: goal-distribution checks (R4), Champions League strength uncertainty (R5), dynamic strengths (R6), promoted-team priors (R7) and a market-disagreement board (R8).
- **Title outrights:** The Odds API has none for these competitions. A title yardstick needs another source, or ratings implied by match odds.
