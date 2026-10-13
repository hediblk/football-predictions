# Roadmap

The goals are good league-winner odds and good Champions League forecasts, from single matches through to the trophy. Title outcomes are too few to tell models apart (50 league-seasons put a standard error of 0.01–0.03 on champion log loss). Model changes are therefore judged on match log loss over all seasons, with the top-three points bias, title metrics and the market as checks. [PLAN.md](PLAN.md) records what is implemented and why.

Recently done: the calibrated xG scale and ridge 2 (Plan C), filling results football-data.org lags on from Understat, the daily [odds archive](data/odds/README.md), Champions League league offsets with one European club scale (Plan D), league levels set by archived Champions League prices (Plan E), and past-date league reruns (`football-predict --as-of`) with dated site history in `site/data/history`, backfilled for 2026/27 and extended by every refresh.

## Next

### 1. Champions League league offsets: follow-ups

The main fix is done (Plan D in [PLAN.md](PLAN.md)). League offsets now shrink toward a typical league level instead of the Premier League, and each club gets a shrunk European effect. Replay log loss fell from 0.9395 to about 0.909. Left to do:

- **Recheck the market weight after MD6.** Archived Champions League prices now set each league's current level (Plan E), which cut the Premier League's lead over La Liga and the Bundesliga by about 40% and put La Liga above Ligue 1. The weight (10 per quote) and shift ridge (5) rest on one matchday of prices; refit them by leave-one-out on prices and score them on results once six matchdays are archived.
- **Serie A looks low.** It sits last of the big five (57.5 against StatsUltra's 69.8); its few priced fixtures barely move it.
- **Europa and Conference League data.** These are where mid-table clubs meet across leagues, so they matter for league levels. football-data.org's free tier refuses the Europa League (paid plans only) and has no Conference League; openfootball stops at 2024/25 plus qualifiers. The Odds API quotes both, and the archive has saved their 1X2 prices since 13 October 2026 (about 36 fixtures per round; 17 of the first 36 involve two clubs the Champions League model rates). Next: test them as extra market rows in the fit (the 10 December recheck does this). Its scores endpoint could also log results from now on for about 4 credits a day; the archive uses 8 of 500 monthly credits a day. 2025/26 results would need another source, such as Wikipedia's match tables or a paid API.

### 2. Title-race charts

Each team's title, top-four, relegation and Champions League stage odds through the season. The data is in place: `site/data/history/<season>/<competition>.json` is backfilled for 2026/27 and gains a point on every day with new results. Left: the charts, on each competition page or in their own tab.

### 3. What's at stake

For the next matchday, how much each result (home, draw, away) moves every team's title, top-four and Champions League odds. It comes from the existing simulations by recording each upcoming fixture's simulated result and conditioning on it, with no extra runs. Show it as badges on Matches and as "games that decide our season" on club pages.

### 4. Clubs tab: a weekly power ranking

The Clubs tab already rates every club overall, in attack and in defence on one scale, but recomputes the ranking at every daily refresh, so nothing shows how clubs move. The changes:

- **Weekly ranking.** Freeze the ranking every Monday, after the weekend round and any midweek Champions League games, and keep each week's ranks.
- **Movement.** Next to every rank, show places gained or dropped since the previous Monday: a green ▲ with the number, a red ▼ with the number, or a dash. Do the same for the attack and defence ranks.
- **Attack and defence up front.** Give the offensive and defensive scores the same prominence as the overall rating, and add the week's biggest risers and fallers.
- **Movement from the first week.** Done: Mondays from 17 August are backfilled in `site/data/history/2026/clubs.json`, and the Monday refresh freezes each new week.
- **Cross-league scale.** Done in Plan D: ratings come from the Champions League model on one European scale (the share of points against an average European top-flight side). Next, let the ranking include Champions League clubs from other leagues, which are already rated in `cl_club_ratings.csv`.
- **Design.** [DESIGN.md](DESIGN.md) reserves green for called results and red for relegation or misses, so record the arrows there as a new use. As with calls, colour never stands alone: always show the arrow and the number.

### 5. Scorecard tab

The track record in proper scores (log loss, RPS, Brier) against always backing the home side, Elo, and the market from the odds archive, with a calibration chart and a rolling view. "Called N of M" moves below these. It needs a few weeks of archived odds first. Champions League forecasts already use earlier archived prices (Plan E), so they are not independent of the market there.

### 6. Players (phase 6)

Lineups, injuries and suspensions, with player ratings that turn an expected starting XI into team strength. A player dataset with ratings for whole squads would give every player a prior, including clubs outside the top five leagues where we have the least data. Check each source's terms before republishing its data on the site. A lineup and injury source is also needed: the API-Football free tier or a paid football-data.org plan. This is the largest effort and the largest remaining source of information.

## Parked

- **Elo K and season regression:** at most 0.0005 log loss in the Plan C search.
- **Non-penalty xG:** npxG, npxGA and PPDA are already in the cached Understat responses, so it is cheap to test. Penalty frequency is partly a team trait, so model it rather than drop it.
- **Promoted teams and preseason priors:** second divisions (E1, SP2, D2, I2, F2) with a division offset. This matters for early-season tables, not title races.
- **Dynamic, score-driven team strengths:** would replace both time decay and Elo, a bigger change.
- **Strength uncertainty in season simulations:** tested and rejected. Title favorites already win as often as forecast, and added noise made title forecasts worse. Revisit only for points ranges or the Champions League offsets.
- **Title outrights:** The Odds API has none for these competitions. A title yardstick needs another source, or ratings implied by match odds.
