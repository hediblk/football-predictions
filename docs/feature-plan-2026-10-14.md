# Feature plan, 14 October 2026

This plan turns the [feature research](football-feature-research-2026-10-14.md) into tasks that one agent session (Codex or Claude) can finish and open as one pull request each. It covers:

- **The match page**, in three phases: existing data, then Understat shots, then ESPN box scores and UEFA running data.
- **Five additions** from the research: the scorecard, weekly race movers, who's beating the model, rating history with club comparison, and games that matter.

It doesn't change [ROADMAP.md](../ROADMAP.md) priorities for the model.

The free sources were checked against real matches on 14 October 2026. All three are unofficial endpoints without published reuse terms. Fetch each finished match once, publish only our derived numbers and our own graphics, credit the source in the footer, and hide a section when its data is missing.

| Source | Endpoint | Gives | Covers |
| --- | --- | --- | --- |
| Understat | `getMatchData/<understat id>` (header `X-Requested-With: XMLHttpRequest`, gzipped), ~5 KB | Every shot: position (0–1), xG, minute, result, situation, body part, shooter, assister. Player rows: minutes, position, shots, xG, xA, key passes, cards, substitutions | Five leagues, no Champions League |
| ESPN | `site.api.espn.com/apis/site/v2/sports/soccer/<league>/scoreboard?dates=YYYYMMDD`, then `summary?event=<id>`; leagues `eng.1, esp.1, ger.1, ita.1, fra.1, uefa.champions` | Box score (possession, shots, passes, tackles, saves, cards), goal/card/substitution timeline, lineups | All six competitions |
| UEFA | `match.uefa.com/v5/matches?competitionId=1&seasonYear=<end year>` for IDs; `matchstats.uefa.com/v1/team-statistics/<id>` and `/v1/player-statistics/<id>` | Distance covered, sprints, top speed, possession by zone, per-player 105×69 heatmaps, average positions | Champions League only, no xG |

No free source with acceptable terms provides running data or heatmaps for the five leagues; FotMob's and Sofascore's terms forbid scraping. Don't add them.

## Rules for every task

**Before starting:** read `AGENTS.md`, `DESIGN.md`, the [site data contract](site-data-contract.md), [ADR 0001](adr/0001-site-model-boundary.md), [ADR 0002](adr/0002-site-browser-checks.md) and this task's section. Each task is one branch and one PR. Do not edit `deferred-notes/`.

**Upgrade the site, don't bloat it:**

- **No new section tab.** The only new route is the match page, reached from rows people already expand.
- **Prefer existing frames.** Each addition goes into an existing frame, replaces one, or is a new frame in a view that already exists. Each task lists its exact UI footprint; stay inside it.
- **Reuse existing components:** outcome bulbs, ruled `board` tables, hairline meters, race-chart lines, rank plates, ▲▼ arrows, chips and expandable rows. No new hues: amber is the lit accent, red is reserved for misses, relegation and losses, green for calls and gains. Charts use ink with dash patterns. Never use colour alone.
- **Hide what has no data.** A frame or row without data is hidden, not filled with dashes. Coverage is stated where data is partial (for example "xG for 8 of 9 games").
- **Every chart has a text equivalent:** a caption sentence, a `<details>` table or `aria-label`s.
- **Phone layouts:** check every change at 375 px.
- **Keep motion rules:** only the existing motion in `DESIGN.md`.

**Football meanings:**

- **Keep the three "expected" quantities apart, with exact labels:** pre-match expected goals (model), observed shot xG (Understat) and projected final points (`xpts`). Model-expected points from games played (`3·P(win) + P(draw)`) is a fourth quantity. Never call it xPts.
- **Label published and reconstructed forecasts.** Published means saved before kickoff (Task 1). Reconstructed means rebuilt from results before match day (`season_match_forecasts`). Say which one every number is.
- **No leakage.** Post-match data never feeds a forecast. Notes made before kickoff use only results before kickoff.
- **Rounding and noise.** History series are whole percentages; state intervals and don't show changes smaller than the task's stated threshold. Stakes keep the noise filter (≥2 points and >3 standard errors) and the display bars in `BIG_STAKE` (title 8; top four and relegation 15; Champions League top eight and top 24 30).
- **Keep failed refreshes honest.** A failed competition refresh keeps its previous files and timestamps. Ingestion failures never fail the refresh.

**Data plumbing:**

- **Exporter:** new published JSON goes through `scripts/build_site_data.py`, or a script called from `scripts/refresh_site.sh`.
- **Contract:** each new file family gets a mapping in `schemas/site/data.schema.json`, checks in `scripts/validate_site_data.py` where a schema can't express them, and a row in `docs/site-data-contract.md`.
- **Model outputs:** a site-only task does not change forecast probabilities or `calibrated_weights.json`. A task that adds an export field keeps the frozen numerical baselines passing.
- **Load on demand:** per-match detail lives in its own files, loaded only when the match page opens, so Tables and Matches stay as fast as today.
- **Ingestion volume:** at most one request per second, never refetch a published derived file, and cache raw payloads under `.cache/`, which is not committed.

**Before opening the PR:**

- Run the checks the change calls for:
  - Exporter or model changes: `python -m pytest -q -p no:cacheprovider` with the flags in `AGENTS.md`.
  - Data changes: `python scripts/validate_site_data.py --data site/data`.
  - Any UI change: `python scripts/check_site.py --site site`. Add the new view or selectors to `routes()` in that script when the task adds UI.
- Update `DESIGN.md` for a new component and `docs/site-data-contract.md` for a new or changed field. Set the task's status in this file's overview to its PR link.
- Python: no docstrings or new tests unless the user asks; `PYTHONDONTWRITEBYTECODE=1`; delete any `__pycache__`.

**Avoiding conflicts between parallel sessions:**

- **New code in new modules:** the match page lives in `site/assets/match.js`, and its markup in its own `view-match` container.
- **CSS:** each task appends one commented block to `style.css` and doesn't restyle shared selectors.
- **Router changes stay small.** Rebase before merge; conflicts in `index.html` and `style.css` are usually resolved by keeping both sides.

## Overview

| Task | Source | Wave | Depends on | Size | Status |
| --- | --- | --- | --- | --- | --- |
| 1. Published forecast receipts | Foundation | A | none | M | [PR #31](https://github.com/hediblk/football-predictions/pull/31) |
| 2. Match page: route and pre-game mode | Phase 1 | A | none | L | [PR #30](https://github.com/hediblk/football-predictions/pull/30) |
| 3. Weekly race movers | Addition 2 | A | none | S | To do |
| 4. Rating history and club comparison | Addition 5 | A | none | M | To do |
| 5. Games that matter | Addition 6 | A | none | S | To do |
| 6. Match page: post-game mode | Phase 1 | B | 2 (uses 1 when merged) | M | To do |
| 7. Who's beating the model | Addition 4 | B | none (uses 1 when merged) | M | To do |
| 8. Scorecard core | Addition 1 | B | 1 | L | To do |
| 9. Match notes: streaks, head-to-head, records | Phase 1 | B | 2 | L | To do |
| 10. Understat shot ingestion | Phase 2 | B | none | M | [PR #33](https://github.com/hediblk/football-predictions/pull/33) |
| 11. Shot report on the match page | Phase 2 | C | 6, 10 | M | To do |
| 12. ESPN box score and timeline | Phase 3 | C | 6 | L | To do |
| 13. UEFA running data and heatmaps (Champions League) | Phase 3 | C | 6 | L | To do |
| 14. Scorecard: market comparison | Addition 1 | D | 8, plus enough archived odds | M | To do |

Tasks in the same wave can run in parallel. **Merge Task 1 first.** Every day without it is a day of published forecasts that can't be recovered later.

**UI footprint by view:**

| View | Changes |
| --- | --- |
| New match page (`#match/<competition>/<id>`) | Tasks 2, 6, 9, 11, 12, 13 |
| Expanded match row (everywhere) | Task 1: origin label wording. Task 2: one "Match page →" link |
| Tables | Task 3: movers block inside "The race so far". Task 7: one column in the projected table |
| Matches | Task 5: "Games that matter" frame (at most three rows). Task 8: "Model record" frame becomes "Scorecard" |
| Clubs: profile | Task 2: a direct "→" to the match page on each game row, and linked call-strip bars. Task 4: chart and compare picker in "Strength". Task 7: cumulative points chart in "Results against the model", rolling xG in "Goals: reality and model" |
| Model | Task 8: "Track record" frame at `#model/scorecard`. Task 14: market rows in it |
| Footer | Tasks 12 and 13: ESPN and UEFA added to the data links |

## Wave A

### Task 1. Published forecast receipts

**Goal:** keep the forecast each fixture actually had before kickoff, so post-match views and the scorecard can show published rather than rebuilt numbers.

**Data:**

- Add `site/data/history/<season>/forecasts/<competition>.json`: `{slug, season, fixtures: {<fixture id>: receipt}}`.
- Each receipt holds `kickoff`, `generated_at` (the run that produced it), `p`, `exp`, `top`, `call`, `btts`, `o25` and `stakes` when the fixture has any. Copy the published fields exactly as `export_matches` writes them.
- On each build, for every fixture of a freshly refreshed competition whose kickoff is after that run's `generated_at`, write or replace its receipt.
- Once the kickoff time has passed, never touch the receipt again. A retained (failed) competition writes no receipts.
- There is no backfill; nothing can be invented after the fact.
- In `export_matches`, finished fixtures that have a receipt take their forecast fields from it and gain `"published": true`. Their `at` becomes the receipt's `generated_at`.
- Fixtures without a receipt keep today's reconstructed fields and get no flag. Update the `rule` text to say so.

**UI** (expanded match panel, "The call" block only):

- Finished game with `published`: "Published before kickoff, from the model run of 05:30 UTC, 12 Oct."
- Finished game without it: "Reconstructed: forecast as of 00:00 UTC on match day, from results before then." This replaces today's "Forecast as of …" line.
- Nothing else changes.

**Contract:** add the new family; add `published` as an optional boolean on match fixtures. The validator checks that each receipt's `generated_at` is before its `kickoff`.

**Done when:** a build twice in a row is idempotent; a forced kickoff in the past freezes the receipt; a retained competition writes nothing; the existing checks pass.

### Task 2. Match page: route and pre-game mode

**Goal:** a page per fixture that gathers everything Floodlight knows before a match. Finished matches use the same page; Task 6 adds their post-game content.

**Routing:**

- `#match/<competition slug>/<fixture id>` opens a new `view-match` container rendered by `site/assets/match.js`.
- The Matches tab stays lit (`aria-current`), the competition subnav is hidden, and a new fixture scrolls to the top.
- An unknown ID shows one note with a link back to `#matches`.

**Entry points:**

- **Expanded match rows:** in `matchPanel`'s link row, add "Match page →" first, before the club links. Every expanded row gets it: Matches, Tables rounds, and the club page's game rows.
- **Club page, without expanding:**
  - Each game row in "Next up", "Games that decide our season" and "Results against the model" gets a dim "→" at its right end that links straight to the match page. It is its own tab stop, labelled "Match page: <home> v <away>"; clicking elsewhere on the row still expands it.
  - Each call-strip bar in "Results against the model" also links to its match page and keeps its hover title.
- No other new links.

**Layout, top to bottom:**

1. **Hero frame.**
   - Legend: "<Competition> · Matchday N", or the Champions League stage.
   - Both crests at 80 px (64 px on phones), with names linking to club profiles.
   - Kickoff in local time, and a small "← Matches, <day>" link to `#matches/<YYYY-MM-DD>`.
   - The poster numeral is the favourite's chance ("Home win 49%"), with the three outcome bulbs under it, styled like the Tables hero.
2. **"The forecast"** frame. Likeliest scores, goals (expected goals, both teams score, over 2.5) and the call. Split `matchPanel` into reusable render functions instead of copying markup; the expanded row keeps its current look.
3. **"What's at stake"** frame. The existing stakes table (`addStakes`) with the same bars; hidden when nothing passes.
4. **"The two sides"** frame. One ruled board: home column, metric label in the middle, away column. Rows:
   - Rating, attack and defence, as values with rank plates and a hairline meter each.
   - League position and points.
   - Projected finish.
   - Last five games across competitions, as W/D/L lamps with scores, oldest first.
   - Goals and xG for and against per game this season, with xG coverage.

   Champions League clubs from outside the five leagues show Champions League rows only.

**Finished fixtures (until Task 6):** the hero shows the final score in place of the numeral, and "The forecast" is titled "The forecast before kickoff".

**Data:** existing JSON only (competition, matches and `clubs.json` files).

**Done when:** an upcoming and a finished fixture route correctly from an expanded row on Matches, Tables rounds and a club page, and from a club page's direct "→" and call-strip bar; `check_site.py` opens both (add them to `routes()`); `DESIGN.md` documents the match page.

### Task 3. Weekly race movers

**Goal:** answer "what changed in the race since last week?" for each competition, including clubs that didn't play.

**Data:**

- Client side, from `history/<season>/<competition>.json`.
- Use the same baseline as the Clubs ranking arrows (`weeklyView` in `clubs.js`): the history point on the last date before the baseline Monday.
- Change = current value in the competition file − baseline value, in percentage points.
- Show only changes of at least 3 points; the series are whole percentages.

**UI** (Tables, inside the existing "The race so far" frame, above the chart):

- A "Movers since Monday <date>" block with up to five rows, sorted by absolute change.
- Each row: crest and name, "before → now", and a diverging bar with a green ▲ or red ▼ and the signed points.
- It follows the selected race chip: title, top four or relegation; for the Champions League, top eight, top 24 or trophy.
- With no qualifying change, show one dim line: "No change of 3 points or more since Monday <date>."
- Optional: a faint vertical rule on the chart at the baseline date.
- Reuse the `.moves` styling from the Clubs "Risers and fallers" frame. No new frame.

**Done when:** it works for every competition and chip; the Tables routes in `check_site.py` select the block where movers exist.

### Task 4. Rating history and club comparison

**Goal:** show how a club's strength has moved, and compare two clubs on the common European scale.

**Data:** `history/<season>/clubs.json` weekly points (`rating, attack, defense`) plus the live point from `clubs.json`. Client side only.

**UI** (club profile, inside the existing "Strength" frame, below the three gauges):

- **Change since Monday:** each gauge's rank line gains a signed change since the baseline Monday ("▲1.2 since 5 Oct"), with the same arrow rules as the ranking.
- **Rating chart:**
  - A small race-chart-style line chart of the weekly series, with chips Overall · Attack · Defence (default Overall).
  - The club is drawn in amber; the x axis is weeks of this season.
  - The caption gives the change since the first week.
- **Comparison:**
  - A native "Compare with" `<select>`: clubs by rating, grouped by league with `<optgroup>`, plus a "Champions League" group for clubs from outside the five leagues.
  - Choosing a club adds it as a dashed ink line, named at the line end, and an outlined second tick on each gauge's meter with its value.
  - The state lives in the URL as `#clubs/<slug>/vs/<other slug>` so comparisons can be shared. Extend the router's argument parsing for this.

**Reuse:** export the comparison renderer so the match page's "The two sides" frame can later add both clubs' rating lines. Don't wire that in this task unless Task 2 has merged.

**Done when:** a profile with and without `vs` renders; `check_site.py` covers a `vs` URL; `DESIGN.md` documents the compare tick.

### Task 5. Games that matter

**Goal:** surface the few upcoming fixtures that swing a race the most, rivals' games included.

**Data:**

- Client side, from the matches files' `stakes`.
- Candidates: fixtures in the next seven days with at least one stakes line passing `BIG_STAKE`.
- Importance: the largest spread (highest minus lowest of the three conditional values) in any shown line. Ties go to the earlier kickoff.

**UI** (Matches view):

- A new frame, "Games that matter · next 7 days", directly above the selected day's fixtures.
- At most three rows, using `matchRow`, so they expand into the same panel.
- Under each row, one dim line with the biggest swing: "Title: Barcelona 93% → 84% if they lose."
- The frame ignores the competition chips and covers all competitions. It is hidden when no fixture passes the bar.

**Done when:** the frame appears and hides correctly; the `#matches` route in `check_site.py` accepts its absence.

## Wave B

### Task 6. Match page: post-game mode

**Goal:** after full time, show the forecast against the outcome and what the result changed. Builds on Task 2; uses Task 1's receipts when merged.

**Modes:** finished fixtures get "After · Before" chips in the hero (default After). Before shows Task 2's frames unchanged; upcoming fixtures show no chips.

**After mode, top to bottom:**

1. **Hero.**
   - The final score set as the poster numeral.
   - Under it, the three outcome bulbs with the ruled box on the result, and one sentence: "The model gave a draw 26%. Published before kickoff." (or "Reconstructed").
2. **"Forecast against result".**
   - The chance the actual score had, and its rank in the likeliest scores.
   - Season context: "The 4th least expected result of 78 in La Liga this season", ranked by the chance given to the actual outcome among finished fixtures in the matches file.
   - A three-row paired board with exact labels: "Expected before kickoff (model)", "Goals" and "Shot xG (Understat)", where available.
3. **"What it changed".**
   - Season chances before and after for both clubs and any rival in the receipt's stakes. Read them from the history file.
   - Verify the semantics in `site_history.add_point`: a point dated D appears to be a run as of D, before D's matches, so "before" is the point at the kickoff date and "after" the next point.
   - Label it "across the refreshes of <d1> and <d2>", since other results that day count too.
   - When the receipt has stakes, show the stakes table as it was before kickoff, with the column that happened lit.
   - Each club's rating change since the baseline Monday, labelled as such and not attributed to this match alone.

**Data:** existing JSON plus receipts. No exporter change.

**Done when:** both modes work for a published and a reconstructed fixture and for a Champions League fixture; `check_site.py` opens a finished fixture's After mode.

### Task 7. Who's beating the model

**Goal:** show which teams have taken more or fewer points than the model expected from the games they've played, beside their rolling chance quality.

**Data:**

- Client side, from the matches files.
- For each team, sum `3·P(win) + P(draw)` over its finished games with a forecast, and compare with actual points.
- Use published fields where `published` is set; state how many games are published.
- Rolling xG: last-5 and last-10 league games, xG for, against and difference, from `xg`, with coverage.

**UI:**

- **Club profile, "Results against the model" frame:** above the call strip, a cumulative line chart. Actual points are a solid ink line and model-expected points a dashed one, by game number.
  - One sentence: "Arsenal have 22 points from games the model expected to yield 18.4 (+3.6)."
  - Count each competition separately; show league games by default when the club has both, with a chip to switch.
- **Club profile, "Goals: reality and model" frame:** add a "Last 5 · Last 10" row of xG for, against and difference, plus a sparkline of the five-game rolling xG difference.
- **Tables, projected table:** one column, "vs model", with signed points to one decimal after the points column. Define it in the table note. Champions League included.

**Done when:** totals reconcile with a manual sum for one club; empty-xG games are excluded and counted in coverage; the existing table layout still fits at 375 px with horizontal scroll.

### Task 8. Scorecard core

**Goal:** a public track record in proper scores, available now and becoming meaningful as published forecasts accumulate. Task 14 adds the market comparison later.

**Data** (exporter):

- Add `site/data/scorecard.json`, with `{generated_at, competitions: {...}, all: {...}}`.
- Each entry: `n`, `n_published`, model log loss, Brier and RPS.
- **Baselines:**
  - A prior-only frequency baseline: each league's home/draw/away shares from the previous five seasons, fixed before the season.
  - Elo-only probabilities where available. This needs `season_match_forecasts` to export its Elo component per played match, as an added field only, with blended probabilities unchanged. The Champions League has no Elo baseline unless the package already produces one.
- Calibration: ten bins of forecast probability, pooled across the three outcomes, with counts.
- A rolling series by week.
- Score published receipts and reconstructed forecasts separately, and also together, labelled.
- `market` is `null` until Task 14.

**UI:**

- **Matches view:** the "Model record · this season" frame becomes "Scorecard · this season". The table columns become:
  - Competition, Played, Log loss (lit), "vs baseline" (signed difference, ▲ green when better), Brier, Called (hit rate), Published share.
  - Exact score and "Avg chance given" leave this table; the Track record frame keeps them.

  Below the table, one line: "Lower is better. A blind one-in-three guess scores 1.099." Then a link: "Calibration and the rolling record →" to `#model/scorecard`.
- **Model view:** a new "Track record" frame at `#model/scorecard`.
  - A reliability chart: amber dots sized by bin count on a ruled grid, with a dashed diagonal.
  - A rolling log loss line for the model against the baseline (solid ink and dashed ink).
  - A short note on sample size, published versus reconstructed forecasts, and two caveats: calibrated seasons are not independent holdouts, and Champions League strengths already include archived market prices.
- **No new section tab.** This replaces ROADMAP item 2's "Scorecard tab" wording; update ROADMAP when merged.

**Done when:** the scores match an independent recomputation for one competition; the frame renders with zero published forecasts; the contract covers `scorecard.json`.

### Task 9. Match notes: streaks, head-to-head, records

**Goal:** a few short, factual notes per fixture: what's on the line before, and what the result meant after. No filler.

**Data** (exporter):

- Add `site/data/notes/<competition>.json`: `{generated_at, fixtures: {<id>: {pre: [...], post: [...]}}}`.
- Cover fixtures that kicked off in the last 14 days or kick off in the next 14.
- Each note is `{kind, text}`, built from fixed templates.
- Sources: the dated result history the model already loads (football-data.co.uk seasons plus the current season). State the first season covered.
- **Note kinds, with thresholds:**
  - **Streaks:** winning, unbeaten, winless, scoring and clean sheets, overall and home/away. At least 5 games.
  - **Head-to-head:** last six meetings, plus "first win at X since <season>" only when the gap is at least three seasons.
  - **Season records:** biggest win, most goals in a game, and the model's biggest upset by chance given.
  - **Post-match:** streaks extended or ended (at least 5).
- Wording is coverage-qualified ("in our records since 1993/94"). At most four notes per side, highest-threshold first.
- Pre-match notes use only results before kickoff.

**UI** (match page):

- One "Notes" frame. Before mode: "On the line", with the pre notes and a "Last meetings" row of six score chips (date and venue on hover/tap). After mode: "What it meant", with the post notes.
- Plain mono sentences, each led by a small lit bulb.
- Hidden when empty.

**Done when:** spot-checks of five notes against the source results pass; no note relies on results after its fixture's kickoff.

### Task 10. Understat shot ingestion

**Goal:** per-match shot and player data for the five leagues. No UI in this task.

**Data:**

- Carry `understat_id` through `attach_xg` into the match forecast output; this is an internal field, not shown on the site.
- A new `scripts/fetch_match_events.py`, called from `refresh_site.sh` after the forecasts:
  - For each finished domestic fixture with an Understat ID and no derived file, fetch `getMatchData` once.
  - Retry missing data for up to seven days after kickoff. Rate limit to 1 request per second; a failure is a warning, never a failed refresh.
- Write `site/data/match/<season>/<competition>/<fixture id>.json`. This family is shared with Tasks 12 and 13; every data key is optional, and the first ingestion task to land creates it.
  - `id, competition, kickoff, sources: {understat: {id, fetched_at}}`.
  - `shots`: compact tuples `[minute, side, x, y, xg, result, situation, body, player, assister]`.
  - `players: {h, a}`: rows with minutes, position, shots, goals, xG, xA, key passes and cards.
  - `retro: [h, d, a]`: after-the-fact outcome chances, from an exact convolution of each side's shot xGs, treating shots as independent. Name that assumption in the contract.
- **Consistency gates:** shot xG sums must match the published match `xg` to within 0.05 per side, and goals from shots plus own goals must equal the score. On failure, publish nothing and log why.
- Backfill the current season once (about 400 requests at present).

**Done when:** the derived files validate and two reruns fetch nothing new; the contract documents the family and its fields.

## Wave C

### Task 11. Shot report on the match page

**Goal:** a compact chance analysis for finished league games, from Task 10's files.

**UI** (match page After mode; one new frame, "Chances", shown only when the file has shots):

- **Shot map:**
  - One full pitch drawn in `--rule` lines on `--panel`, home shooting right, away shooting left.
  - Circle area proportional to xG. Goals are filled amber bulbs, saved shots filled `--ink-2`, everything else outlined.
  - Tap or hover shows the player, minute, xG and situation.
  - A `<details>` "Shot list" table is the text equivalent.
- **Cumulative xG timeline:**
  - Step lines, home solid ink and away dashed, minutes 0 to the end of stoppage time.
  - Goals are amber bulbs on the scoring side's line, with minute and scorer.
- **"From the chances" row:** the retrospective home/draw/away chances as three small numbers, labelled "after the fact, from shot xG, not a forecast". Don't use the forecast bulbs, so the two can't be confused.
- **"Standouts" row:** the top three players by xG + xA, with minutes, shots, xG, xA and key passes.

Leave the expanded match row unchanged.

**Done when:** it renders on desktop and at 375 px; `check_site.py` opens a finished league fixture with shots; `DESIGN.md` documents the shot map and timeline.

### Task 12. ESPN box score and timeline

**Goal:** team statistics and the goal and card timeline for every competition.

**Data:**

- Map fixtures to ESPN events using the scoreboard per competition and date, with normalised team names and a small committed override map. Store the event ID.
- Add to the shared per-match file:
  - `box`: possession, shots, shots on target, corners, fouls, offsides, saves, pass accuracy, yellow and red cards.
  - `events`: minute, type (goal, own goal, penalty goal, missed penalty, yellow, red, substitution), side and player names.
  - The ESPN event ID under `sources`.
- Same fetch-once, retry and warning rules as Task 10. Check that ESPN's final score matches ours before publishing.

**UI:**

- **New "Match stats" frame in the match page's After mode:**
  - At most ten rows of paired bars on a common scale per row: home left, away right, values at the ends. The larger value is bold, not coloured.
  - Goals and red cards become markers on Task 11's xG timeline. Where there are no shots (the Champions League), a compact minute ruler with goal and card glyphs and scorer names is shown instead.
  - Substitutions appear only in a collapsed "Full timeline" `<details>`.
- **Footer:** add "ESPN · match statistics" to the data links.

**Done when:** at least 95% of last week's finished fixtures map, and unmapped ones are listed in the run output; renders for a league and a Champions League fixture.

### Task 13. UEFA running data and heatmaps (Champions League)

**Goal:** distance, sprints, top speed and where each side played, for Champions League games.

**Data:**

- Map fixtures to UEFA match IDs from the season listing, by date and teams. Store the ID.
- Add to the shared per-match file:
  - `physical`: per team, distance in km, sprints and top speed; per player, minutes, distance and top speed.
  - `heat`: per team, the sum of players' 105×69 heatmaps downsampled to 21×14 integers; per player, the same for anyone who played at least 30 minutes.
  - `positions`: average positions of the starters, with shirt numbers.
- Check the file size; keep each match file under 60 KB. Same fetch rules as Task 10.

**UI:**

- **Match page After mode, Champions League only:**
  - Add distance, sprints and top speed as rows in Task 12's "Match stats" frame (or create that frame if Task 12 hasn't merged).
  - One new frame, "Where they played": a pitch drawn as a grid of bulbs whose brightness is the share of activity (the existing bulb signature, no new colour).
  - Chips Home · Away, a native player `<select>` for one player's map, and an average-positions overlay of numbered dots for the starters.
- **Footer:** add "UEFA · match data".

**Done when:** it renders for a finished Champions League fixture at desktop width and at 375 px; the size limit holds across a matchday.

## Wave D

### Task 14. Scorecard: market comparison

**Goal:** compare the model with bookmaker prices on the same matches.

**Start when:** at least 300 domestic fixtures have an archived quote observed before both the published forecast's run and kickoff. The archive started on 13 October 2026; at about 50 league fixtures a week this is expected around December 2026. Check the count with a short script first; if it's short of 300, stop.

**Data:**

- Margin-free market probabilities from `data/odds` (follow its README for quote expiry and matching).
- Score only matched fixtures, against the model's published receipts on the same set.
- Report `n`, the log-loss difference and a bootstrap 90% interval.
- Fill `scorecard.json`'s `market`. Champions League rows are marked as not independent (Plan E).

**UI:**

- **Matches scorecard table:** add a "vs market" column, "–" below the threshold.
- **Model "Track record" frame:** add a scatter of model against market home-win chance on matched fixtures (ink dots, dashed diagonal, n in the caption) and the market's line on the rolling chart (a third dash pattern).

**Done when:** matching respects observation and kickoff times; the interval and `n` are shown wherever the comparison is.
