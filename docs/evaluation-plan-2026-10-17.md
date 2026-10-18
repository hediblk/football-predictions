# How we miss, and recap cards: plan, 17 October 2026

The scorecard says how good the forecasts are (log loss, Brier, RPS, calls). It doesn't say **how** they go wrong. This plan adds that, using the observed xG and shot timings we already collect, and adds downloadable cards whose verdict line uses the same classification.

## What this season already shows

The 301 finished league matches with forecasts this season, on 17 October:

| Called \ actual | Home | Draw | Away |
| --- | ---: | ---: | ---: |
| Home | 106 | 52 | 38 |
| Draw | 0 | 0 | 0 |
| Away | 30 | 24 | 51 |

- **157 of 301 calls are right (52%).** Of the 144 misses, **76 are draws (53%)** and 68 are upsets.
- **Draws aren't the weakness they look like.** The model expected 74.3 draws and got 76. It never *calls* a draw (the highest draw probability this season is 32.6%), because a draw is almost never the single most likely outcome. That makes call accuracy a poor yardstick, not the model a poor draw predictor.
- **Half the upsets were won on chances.** In 34 of the 68 upsets, the team we favoured had more xG; in the other 34 it didn't. Draws split the same way (37 against 38). This split uses any xG lead; the definitions below use a 0.5 margin.
- **Our favourite won the xG battle in 70% of games** (209 of 300), against 52% of results.
- **Expected goals track xG better than goals.** Mean absolute error per team-game: 0.70 against observed xG, 0.94 against actual goals. Predicted goals average 1.41 per team-game, below this season's 1.54 goals and 1.69 xG; Task 1 checks whether that is systematic.

RPS, already on the scorecard, is the ordinal score the brainstorm asked for: calling a home win is penalised less when the game is drawn than when the away side wins. The new views explain the misses; they don't replace log loss as the yardstick.

## Definitions

- **Call:** the outcome with the highest forecast probability; exact ties resolve home, draw, away. **Favourite:** whichever of home and away has the higher win probability, even when a draw is the call; exact home/away ties resolve home.
- **Miss kind:** `called` when the call happened; otherwise `missed_draw_call` when the call was a draw; otherwise `draw` when the favourite drew, or `upset` when the favourite lost. This precedence makes the four kinds exhaustive, including the 29 missed draw calls in the historical report.
- **On chances:** compare the two sides' observed xG. An absolute difference **≤0.5 xG** is `level`; otherwise the favourite `won` or `lost` on xG. With no valid xG pair (Champions League, missing observations) it is `unknown`, never guessed. Task 1 recommends retaining 0.5 as a display tolerance, not an empirically optimal threshold or proof of a deserved result.
- **Before the first goal (offline only):** shots strictly before the first goal event's integer minute, including own goals as stopping events but excluding their xG; all shots in goalless games. Minute-only timing excludes every shot in the scoring minute. The report audits the draft's early-as-`level` rule, but any future use should mark first goals at elapsed minute <10 as `unknown` (insufficient play). Task 1 rejects this lens for the site: 55.1% disagree with the whole-game verdict, mostly because short intervals become level. It is not a causal correction for game state; no `xg_pre` field or toggle is planned.
- **On-chances probabilities:** home, draw and away probabilities implied by the observed xG, from two independent Poissons with the observed xG as means. They describe an independent-Poisson replay of the observed chance totals, beside our pre-match forecast; they are not a causal or deserved-result claim.
- **xG-scored log loss:** cross entropy against the on-chances probabilities instead of the actual result. Report it beside real log loss on the same xG-covered fixtures. Task 1 finds smaller clustered SEs but reversals in candidate-model rankings: it measures a different target and must not be used to select or tune the production model. Use the same observed-xG vintage as the displayed match totals; do not silently substitute shot-payload xG.

## Tasks

| Task | Area | Wave | Depends on | Size | Status |
| --- | --- | --- | --- | --- | --- |
| 1. Eleven-season miss report | Offline analysis | 1 | none | M | [PR #64](https://github.com/hediblk/football-predictions/pull/64) |
| 2. Match, round and race cards | UI | 1 | none (verdict line after 3) | L | [PR #65](https://github.com/hediblk/football-predictions/pull/65) |
| 3. Miss breakdown in the scorecard export | Data | 2 | 1 | M | To do |
| 4. "How we miss" on the site | UI | 2 | contract below (data from 3) | M | [PR #67](https://github.com/hediblk/football-predictions/pull/67) |

**Order:** the report runs first, because it may change the margin, the before-first-goal lens or the goal-level picture that the site would show. Cards don't depend on it and run alongside. Tasks 3 and 4 start once the report merges, with the contract below updated to its findings.

**Rules:** those of the [feature plan](feature-plan-2026-10-14.md) apply: the site data contract, schema and validator for new fields; no new top-level tab; existing components; published and reconstructed forecasts labelled; coverage stated where partial; every graphic with a text equivalent; checks at 375 px. No forecast, default or calibration changes.

### Contract (Task 1 recommendations; implement in Task 3)

Each scorecard record (`all`, each competition, and their `published` and `reconstructed` cohorts) gains:

```json
"misses": {
  "confusion": [[106, 52, 38], [0, 0, 0], [30, 24, 51]],
  "outcomes": {"expected": [129.8, 74.3, 96.9], "actual": [136, 76, 89]},
  "kinds": {"draw": {"xg": {"won": 0, "level": 0, "lost": 0, "unknown": 0}},
            "upset": {"xg": {"won": 0, "level": 0, "lost": 0, "unknown": 0}},
            "called": {"xg": {"won": 0, "level": 0, "lost": 0, "unknown": 0}},
            "missed_draw_call": {"xg": {"won": 0, "level": 0, "lost": 0, "unknown": 0}}},
  "goals": {"team_games": 600, "predicted": 1.41, "goals": 1.54, "xg": 1.69,
            "mae_goals": 0.94, "mae_xg": 0.70},
  "xg_scored": {"model": {"n": 300, "log_loss": 0.0, "real_log_loss": 0.0},
                "elo": {"n": 300, "log_loss": 0.0, "real_log_loss": 0.0},
                "frequency": {"n": 300, "log_loss": 0.0, "real_log_loss": 0.0}}
}
```

`confusion` rows are the call (home, draw, away) and columns the result. The matrix, all four kinds combined, and actual outcome counts each sum to the scorecard's `n`; expected counts sum to `n` within floating-point tolerance. Kinds include unknown-xG matches. `goals` covers fixtures with both valid observed xG and stored expected-goal pairs; `team_games` is twice that count. `predicted` comes from the blended scoreline distribution, not unblended Poisson rates. MAEs average absolute errors per team-game. Each `xg_scored` comparator has its own xG-covered denominator and corresponding real log loss on those exact fixtures; unavailable comparators use `n: 0` and null losses. Do not fill missing five-season frequency history with a shorter or future window. Clustered SEs belong to the offline report, not this initial site contract. Each finished fixture in `matches/<competition>.json` gains:

```json
"miss": {"kind": "called|draw|upset|missed_draw_call", "xg": "won|level|lost|unknown"},
"xg_p": [0.61, 0.24, 0.15]
```

These use the same forecast the scorecard uses (the receipt when published). `xg_p` is absent without xG and uses the independent-Poisson definition above, distinct from existing shot-Bernoulli retrospective probabilities. Values above are illustrative. No site fields or schema are changed by Task 1.

**Task 1 evidence:** [report](eleven-season-miss-report.md), [complete tables with clustered SEs](eleven-season-miss-report-tables.md). The 19,763-match replay has 19,759 validated xG pairs and 19,756 valid shot histories. Its offline outputs retain every draft-contract quantity, including `xg_pre`, for audit. Recommendations: retain 0.5; keep argmax calls; show actual goals separately from xG; omit the pre-goal lens; keep xG-scored loss diagnostic only. Historical actual-goal bias is −0.0031 ± 0.0068 per team-game; xG-scored and real-loss candidate ranks have Spearman 0.282 (bootstrap 95% interval 0.182–0.409).

### Task 1. Eleven-season miss report

- Use the [forecast-calibration](../packages/forecast-calibration/README.md) dataset: 19,763 matches, 2015/16–2025/26, each forecast before kickoff, with Understat xG. Score the no-odds blend. Shot timings for the before-first-goal lens are in the raw Understat match responses in the main checkout's `.cache/understat/matches/` (21,589 games; see [data/players/understat/README.md](../data/players/understat/README.md)).
- Report everything in the contract, by league and season, with clustered SEs. Then answer:
  - **Draws:** are draw probabilities calibrated by bin, and by how close the two sides are? How often is a draw the most likely outcome, and would calling draws more often ever improve accuracy or log loss?
  - **Goal level:** is this season's predicted-goals deficit systematic or seasonal, and does it differ by league?
  - **The margin:** how do the won / level / lost shares move between 0.3, 0.5 and 0.7 xG? Recommend one.
  - **Game state:** how often do the whole-game and before-first-goal verdicts disagree, and in which direction? Is the before-first-goal lens worth showing on the site?
  - **xG-scored log loss as a selection aid:** does ranking candidate models by it agree with ranking by real log loss on the same matches, and how much does it shrink the noise? Do not use it to tune the production model.
- Put the report in `docs/` and outputs in `out/`. Update this plan's definitions and contract to the recommendations. No model changes.
- **Done when:** each question has an answer with its uncertainty; a "no" is a valid answer.

### Task 2. Match, round and race cards

Cards are drawn client-side on a canvas from data each page already has, and saved as PNG: 1080×1350 portrait, plus 1200×675 landscape for X. Wait for `document.fonts.ready` before drawing; crests are local, so the canvas stays untainted. Follow [DESIGN.md](../DESIGN.md): the scoreboard look, existing tokens and fonts, the Floodlight mark and URL in the footer, sources credited. No new hues. Nothing is posted to social accounts. Each card's page is its text equivalent, and each "Download card" chip has a clear label.

- **Match preview card** (match page, Before mode): competition and kickoff, crests and names, the three outcome bulbs with percentages, expected goals, the most likely score, and the stakes tag when the game has one.
- **Full-time card** (match page, After mode): final score, xG where known, our pre-match probabilities labelled published or reconstructed, and the on-chances probabilities from xG. Add the verdict line ("Called it" / "Drew; we had the better chances" / "Upset; they had the better chances") once Task 3's `miss` field exists.
- **Round card** (Matches, a day or round view): "How we did": calls right out of games, misses split into draws, upsets and missed draw calls, the round's log loss against Elo, and the best and worst calls (highest probability on the actual result and the biggest upset).
- **Race card** (Tables, "The race so far"): the competition's title, top-four and relegation chances with this week's movers and arrows, as the movers block shows them.
- **Done when:** every card renders for a league with xG, the Champions League (no xG) and an upcoming match. Files download at both sizes with legible text, and `check_site.py` clicks each chip without errors.

### Task 3. Miss breakdown in the scorecard export

- Extend `src/standing_prediction/scorecard.py` and the exporter with the `misses` block, the per-fixture `miss` and `xg_p` fields, using Task 1's 0.5 margin and whole-game xG only. Include the `missed_draw_call` edge case; do not compute or export the rejected pre-goal lens. Combine cohorts the way `combine_records` does.
- Update `schemas/site/data.schema.json`, `scripts/validate_site_data.py` (the confusion matrix sums to `n`, all four kinds sum to `n` (the three non-`called` kinds sum to misses), outcome counts reconcile, and each `xg_p` sums to 1) and `docs/site-data-contract.md`.
- **Done when:** the season numbers reproduce from the published data, an identical rebuild changes nothing, and pytest, validation and the browser check pass.

### Task 4. "How we miss" on the site

- **Model → Track record:** a new "How we miss" block after calibration:
  - the 3×3 called-against-actual table as a ruled `board`, with counts and row shares;
  - a split meter of draw misses and upsets, each split by won / level / lost on whole-game chances, with unknown coverage stated and missed draw calls shown separately when nonzero;
  - expected against actual home, draw and away counts;
  - one line on goals: predicted, actual and xG per team-game, and the two errors;
  - xG-scored log loss beside the real log loss, clearly labelled as a diagnostic.
- **Matches → Scorecard:** one compact line, such as "Misses: 76 draws, 68 upsets; half the upsets won on chances", linking to the block.
- **Match page, After mode:** an "On chances" row of the three outcome bulbs from `xg_p` next to the pre-match forecast, and a verdict tag from `miss`.
- Follow the published/reconstructed toggle the scorecard already has, and state the xG coverage.
- **Done when:** it renders for all competitions, the Champions League (no xG) says so, and `check_site.py` covers the block at desktop and 375 px.
