# Roadmap

The goals are good league-winner odds and good Champions League forecasts, from single matches through to the trophy. Title outcomes are too few to tell models apart (50 league-seasons put a standard error of 0.01–0.03 on champion log loss). Model changes are therefore judged on match log loss over all seasons, with the top-three points bias, title metrics and the market as checks. [PLAN.md](PLAN.md) records what is implemented and why.

Recently done: the calibrated xG scale and ridge 2 (Plan C), filling results football-data.org lags on from Understat, the daily [odds archive](data/odds/README.md), Champions League league offsets with one European club scale (Plan D), league levels set by archived Champions League prices (Plan E), and past-date league reruns (`football-predict --as-of`) with dated site history in `site/data/history`, backfilled for 2026/27 and extended by every refresh, which feeds the title-race charts on each competition page, what's at stake for the next round's games (Matches and club pages; Champions League top eight, top 24 and trophy too) and the Clubs tab's weekly power ranking with movement arrows, which now includes the Champions League clubs from outside the five leagues.

The site/model boundary is also checked: offline numerical regressions, exporter tests, a published-data contract, and validation of the exact revision deployed. The model and site keep their existing folders and separate CI workflows. See [ADR 0001](docs/adr/0001-site-model-boundary.md). Every view is also loaded in headless Chromium on site pull requests and before each deploy, and deployed asset URLs carry a content version so browsers never mix cached code with new files ([ADR 0002](docs/adr/0002-site-browser-checks.md)).

The [football feature research (14 October 2026)](docs/football-feature-research-2026-10-14.md) compares established stats and prediction sites and their social formats, with 36 feature ideas and their data requirements. Recommended starting points are dedicated post-match reports, round race movers, shareable cards, rolling xG and points-versus-pre-match-expectation charts. Shot maps and xG timelines depend on individual-shot data. The [feature plan (14 October 2026)](docs/feature-plan-2026-10-14.md) splits the match page (pre-game, post-game, shots, box scores and Champions League running data), the scorecard, race movers, rating history, games that matter and who's beating the model into fourteen tasks, each sized for one agent session and one PR.

## Next

### 1. Champions League league offsets: follow-ups

The main fix is done (Plan D in [PLAN.md](PLAN.md)). League offsets now shrink toward a typical league level instead of the Premier League, and each club gets a shrunk European effect. Replay log loss fell from 0.9395 to about 0.909. Left to do:

- **Recheck the market weight after MD6.** Archived Champions League prices now set each league's current level (Plan E), which cut the Premier League's lead over La Liga and the Bundesliga by about 40% and put La Liga above Ligue 1. The weight (10 per quote) and shift ridge (5) rest on one matchday of prices; refit them by leave-one-out on prices and score them on results once six matchdays are archived.
- **Serie A looks low.** It sits last of the big five (57.5 against StatsUltra's 69.8); its few priced fixtures barely move it.
- **Europa and Conference League data.** These are where mid-table clubs meet across leagues, so they matter for league levels. football-data.org's free tier refuses the Europa League (paid plans only) and has no Conference League; openfootball stops at 2024/25 plus qualifiers. The Odds API quotes both, and the archive has saved their 1X2 prices since 13 October 2026 (about 36 fixtures per round; 17 of the first 36 involve two clubs the Champions League model rates). Finished [results come from ESPN for 2025/26 onward](data/results/README.md), backfilled and appended daily without a key; The Odds API scores endpoint is no longer needed. [Coverage and club-name matches](docs/el-ecl-results-coverage.md) are recorded separately. The model does not use these results yet. Next: test the archived results and prices as cross-league evidence in the 10 December recheck.

### 2. Scorecard in Matches and Model

The Matches scorecard and Model Track record frame show log loss, RPS and Brier against each competition’s prior five-season outcome frequencies and Elo, with calibration counts and cumulative weekly scores. Published receipts and reconstructed forecasts are reported separately and together. The market comparison (feature-plan Task 14) remains pending until at least 300 published domestic fixtures have eligible archived quotes. Champions League forecasts already use earlier archived prices (Plan E), so they are not independent of the market there.

### 3. Players (phase 6)

The [La Liga ideal-XI pilot](docs/squad-matching.md) matches current API squads to EA ratings, freezes position-constrained XIs, and compares actual starts, substitute appearances and minutes from collected match data. Its local reports keep older-game diagnostics separate from prospective observations. The UEFA identity cross-check resolves all 129 heatmap-player and 110 starter records for the five pilot clubs represented in ten Champions League club-games.

The [squads and players plan](docs/xi-ui-plan-2026-10-15.md) splits the next steps into agent-sized tasks. EA SPORTS FC is the only rating source and is credited on the site. Playing time comes from match sheets (Understat for domestic games, UEFA lineups for the Champions League); heatmaps show observed position, not minutes. First a squad export for all 111 supported clubs and a club **Squad** subtab (ideal XI, squad table, then playing time and XI history), with Understat lineups since 2014/15 collected alongside. Then EA rating vintages, a pooled xG plus-minus model with EA ratings as the prior, and an expected-XI forecast adjustment, kept only with a measured gain. One model per team is ruled out: about 38 games a season are too few to separate a player's effect from noise. Injuries, confirmed-XI forecasts and boosting are later nice-to-haves.

Remaining work includes identity coverage, historical rating vintages, dated pre-kickoff lineups, source redistribution terms and evaluation. Existing domestic match sheets and UEFA lineup/physical records supply historical starters/minutes; heatmap grids alone do not. Unused bench, injuries and suspensions need additional evidence. The current pilot changes neither published player data nor forecast probabilities.

## Parked

- **Repository rename:** deferred. GitHub redirects remotes but not the Pages address; preserve existing links or set up a custom domain before renaming.
- **Elo K and season regression:** at most 0.0005 log loss in the Plan C search.
- **Non-penalty xG:** npxG, npxGA and PPDA are already in the cached Understat responses, so it is cheap to test. Penalty frequency is partly a team trait, so model it rather than drop it.
- **Promoted teams and preseason priors:** second divisions (E1, SP2, D2, I2, F2) with a division offset. This matters for early-season tables, not title races.
- **Dynamic, score-driven team strengths:** would replace both time decay and Elo, a bigger change.
- **Strength uncertainty in season simulations:** tested and rejected. Title favorites already win as often as forecast, and added noise made title forecasts worse. Revisit only for points ranges or the Champions League offsets.
- **Title outrights:** The Odds API has none for these competitions. A title yardstick needs another source, or ratings implied by match odds.
