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

- **Call:** the outcome with the highest forecast probability. **Favourite:** whichever of home and away has the higher win probability, even when a draw is the call.
- **Miss kind:** `called` (the call happened), `draw` (the favourite drew) or `upset` (the favourite lost).
- **On chances:** compare the two sides' observed xG. Within **0.5 xG** is `level`; otherwise the favourite `won` or `lost` on xG. With no xG (Champions League, missing sheets) it is `unknown`, never guessed. Task 1 checks the margin and may change it before Task 3 uses it.
- **Before the first goal:** the same comparison using only shots before the first goal, or all shots in a goalless game, from Understat shot timings. A side that scores early and then sits back stops flattering its opponent's xG. It is `unknown` without shot data, and `level` when the first goal comes within ten minutes, since too little play precedes it.
- **On-chances probabilities:** home, draw and away probabilities implied by the observed xG, from two independent Poissons with the observed xG as means. They show what the chances "deserved", beside our pre-match forecast.
- **xG-scored log loss:** log loss against the on-chances probabilities instead of the actual result. It's a lower-noise diagnostic of whether we forecast the game's chances, but it rewards agreeing with Understat's xG model. Report it beside the real log loss, never instead of it.

## Tasks

| Task | Area | Wave | Depends on | Size | Status |
| --- | --- | --- | --- | --- | --- |
| 1. Eleven-season miss report | Offline analysis | 1 | none | M | To do |
| 2. Match, round and race cards | UI | 1 | none (verdict line after 3) | L | To do |
| 3. Miss breakdown in the scorecard export | Data | 2 | 1 | M | To do |
| 4. "How we miss" on the site | UI | 2 | contract below (data from 3) | M | To do |

**Order:** the report runs first, because it may change the margin, the before-first-goal lens or the goal-level picture that the site would show. Cards don't depend on it and run alongside. Tasks 3 and 4 start once the report merges, with the contract below updated to its findings.

**Rules:** those of the [feature plan](feature-plan-2026-10-14.md) apply: the site data contract, schema and validator for new fields; no new top-level tab; existing components; published and reconstructed forecasts labelled; coverage stated where partial; every graphic with a text equivalent; checks at 375 px. No forecast, default or calibration changes.

### Contract (draft until Task 1 merges)

Each scorecard record (`all`, each competition, and their `published` and `reconstructed` cohorts) gains:

```json
"misses": {
  "confusion": [[106, 52, 38], [0, 0, 0], [30, 24, 51]],
  "outcomes": {"expected": [129.8, 74.3, 96.9], "actual": [136, 76, 89]},
  "kinds": {"draw": {"xg": {"won": 0, "level": 0, "lost": 0, "unknown": 0},
                     "xg_pre": {"won": 0, "level": 0, "lost": 0, "unknown": 0}},
            "upset": {"xg": {}, "xg_pre": {}}, "called": {"xg": {}, "xg_pre": {}}},
  "goals": {"team_games": 600, "predicted": 1.41, "goals": 1.54, "xg": 1.69,
            "mae_goals": 0.94, "mae_xg": 0.70},
  "xg_scored": {"n": 300, "model": 0.0, "elo": 0.0, "frequency": 0.0}
}
```

`confusion` rows are the call (home, draw, away) and columns the result. `goals` and `xg_scored` cover only matches with observed xG; `team_games` and `n` say how many. Each finished fixture in `matches/<competition>.json` gains:

```json
"miss": {"kind": "called|draw|upset", "xg": "won|level|lost|unknown", "xg_pre": "won|level|lost|unknown"},
"xg_p": [0.61, 0.24, 0.15]
```

These use the same forecast the scorecard uses (the receipt when published). `xg_p` is absent without xG. Values above are illustrative.

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
- **Round card** (Matches, a day or round view): "How we did": calls right out of games, misses split into draws and upsets, the round's log loss against Elo, and the best and worst calls (highest probability on the actual result and the biggest upset).
- **Race card** (Tables, "The race so far"): the competition's title, top-four and relegation chances with this week's movers and arrows, as the movers block shows them.
- **Done when:** every card renders for a league with xG, the Champions League (no xG) and an upcoming match. Files download at both sizes with legible text, and `check_site.py` clicks each chip without errors.

### Task 3. Miss breakdown in the scorecard export

- Extend `src/standing_prediction/scorecard.py` and the exporter with the `misses` block, the per-fixture `miss` and `xg_p` fields, using Task 1's margin and lenses. Compute the before-first-goal lens from the published match files' shots. Combine cohorts the way `combine_records` does.
- Update `schemas/site/data.schema.json`, `scripts/validate_site_data.py` (the confusion matrix sums to `n`, the kinds sum to the misses, outcome counts reconcile, and each `xg_p` sums to 1) and `docs/site-data-contract.md`.
- **Done when:** the season numbers reproduce from the published data, an identical rebuild changes nothing, and pytest, validation and the browser check pass.

### Task 4. "How we miss" on the site

- **Model → Track record:** a new "How we miss" block after calibration:
  - the 3×3 called-against-actual table as a ruled `board`, with counts and row shares;
  - a split meter of the misses: draws on the left, upsets on the right, each split by won / level / lost on chances, with a toggle for the before-first-goal lens if Task 1 recommends it;
  - expected against actual home, draw and away counts;
  - one line on goals: predicted, actual and xG per team-game, and the two errors;
  - xG-scored log loss beside the real log loss, clearly labelled as a diagnostic.
- **Matches → Scorecard:** one compact line, such as "Misses: 76 draws, 68 upsets; half the upsets won on chances", linking to the block.
- **Match page, After mode:** an "On chances" row of the three outcome bulbs from `xg_p` next to the pre-match forecast, and a verdict tag from `miss`.
- Follow the published/reconstructed toggle the scorecard already has, and state the xG coverage.
- **Done when:** it renders for all competitions, the Champions League (no xG) says so, and `check_site.py` covers the block at desktop and 375 px.
