# Roadmap

The goals are good league-winner odds and good Champions League forecasts, from single matches through to the trophy. Title outcomes are too few to tell models apart (50 league-seasons put a standard error of 0.01–0.03 on champion log loss). Model changes are therefore judged on match log loss over all seasons, with the top-three points bias, title metrics and the market as checks. [PLAN.md](PLAN.md) records what is implemented and why.

Recently done: the calibrated xG scale and ridge 2 (Plan C), filling results football-data.org lags on from Understat, and the daily [odds archive](data/odds/README.md).

## Next

### 1. Champions League league offsets (highest priority)

**Problem.** League offsets learned from European matches put Ligue 1 above the Premier League (+0.09 on the log goal-rate scale) and Ukraine above Portugal, the latter on about three effective European matches. Manchester City sits at 2.3% to win the Champions League and Liverpool at 0.5%, against about 10% each from bookmakers in August. European evidence comes mostly from each league's top clubs, so one club's record (Paris Saint-Germain's) moves every club in its league.

**Options to test:**
- Club-level European effects with shrinkage, so a club's European record attaches to that club rather than its league.
- A league-strength prior from an outside index, such as the Opta league ratings the Clubs tab already uses, updated by European results.
- More European matches. Europa and Conference League games bring mid-table clubs and pin down league averages better; first check what the openfootball supplement already covers.

**Measure:** the 306-match replay (`football-ucl --evaluate`), split by xG coverage, and current title odds against bookmaker prices.

### 2. Title-race charts

Each team's title, top-four, relegation and Champions League stage odds through the season. Backfill 2026/27 by rerunning at past dates, which needs an `--as-of` option for league runs like the one `football-ucl` has. Then append a point at every refresh. This could be a chart on each competition page or its own tab.

### 3. What's at stake

For the next matchday, how much each result (home, draw, away) moves every team's title, top-four and Champions League odds. It comes from the existing simulations by recording each upcoming fixture's simulated result and conditioning on it, with no extra runs. Show it as badges on Matches and as "games that decide our season" on club pages.

### 4. Scorecard tab

The track record in proper scores (log loss, RPS, Brier) against always backing the home side, Elo, and the market from the odds archive, with a calibration chart and a rolling view. "Called N of M" moves below these. It needs a few weeks of archived odds first.

### 5. Players (phase 6)

Lineups, injuries and suspensions, with player ratings that turn an expected starting XI into team strength. Andrew's FM26 dataset can rate every player, including squads outside the top five leagues where we have the least data. Football Manager data belongs to Sports Interactive, so use it for modelling and don't republish raw attributes. A lineup and injury source is also needed: the API-Football free tier or a paid football-data.org plan. This is the largest effort and the largest remaining source of information.

## Parked

- **Elo K and season regression:** at most 0.0005 log loss in the Plan C search.
- **Non-penalty xG:** npxG, npxGA and PPDA are already in the cached Understat responses, so it is cheap to test. Penalty frequency is partly a team trait, so model it rather than drop it.
- **Promoted teams and preseason priors:** second divisions (E1, SP2, D2, I2, F2) with a division offset. This matters for early-season tables, not title races.
- **Dynamic, score-driven team strengths:** would replace both time decay and Elo, a bigger change.
- **Strength uncertainty in season simulations:** tested and rejected. Title favorites already win as often as forecast, and added noise made title forecasts worse. Revisit only for points ranges or the Champions League offsets.
- **Title outrights:** The Odds API has none for these competitions. A title yardstick needs another source, or ratings implied by match odds.
