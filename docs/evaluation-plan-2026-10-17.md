# How we miss, and recap cards: plan, 17 October 2026

The scorecard says how good the forecasts are (log loss, Brier, RPS, calls). It doesn't say **how** they go wrong. This plan adds that, using the observed xG we already collect, and adds downloadable preview and full-time cards whose verdict line uses the same classification.

## What this season already shows

The 301 finished league matches with forecasts this season, on 17 October:

| Called \ actual | Home | Draw | Away |
| --- | ---: | ---: | ---: |
| Home | 106 | 52 | 38 |
| Draw | 0 | 0 | 0 |
| Away | 30 | 24 | 51 |

- **157 of 301 calls are right (52%).** Of the 144 misses, **76 are draws (53%)** and 68 are upsets.
- **Draws aren't the weakness they look like.** The model expected 74.3 draws and got 76. It never *calls* a draw (the highest draw probability this season is 32.6%), because a draw is almost never the single most likely outcome. That is correct behaviour; it makes call accuracy a poor yardstick, not the model a poor draw predictor.
- **Half the upsets were won on chances.** In 34 of the 68 upsets, the team we favoured had more xG; in the other 34 it didn't. Draws split the same way (37 against 38).
- **Our favourite won the xG battle in 70% of games** (209 of 300), against 52% of results.
- **Expected goals track xG better than goals.** Mean absolute error per team-game: 0.70 against observed xG, 0.94 against actual goals. Predicted goals average 1.41 per team-game, below this season's 1.54 goals and 1.69 xG. That is worth checking over more seasons (Task 3).

RPS, already on the scorecard, is the ordinal score the brainstorm asked for: calling a home win is penalised less when the game is drawn than when the away side wins. The new views explain the misses; they don't replace log loss as the yardstick.

## Definitions

- **Call:** the outcome with the highest forecast probability. **Favourite:** whichever of home and away has the higher win probability, even when a draw is the call.
- **Miss kind:** `called` (the call happened), `draw` (favourite drew) or `upset` (favourite lost).
- **On chances:** compare the two sides' observed xG. Within 0.3 is `level`; otherwise the favourite `won` or `lost` on xG. With no xG (Champions League, missing sheets) it is `unknown`, never guessed.
- **xG-scored log loss:** log loss against the outcome distribution implied by the observed xG (two independent Poissons with the observed xG as means), instead of the actual result. It's a lower-noise diagnostic of whether we forecast the game's chances, but it rewards agreeing with Understat's xG model. Report it beside the real log loss, never instead of it.

## Tasks

| Task | Area | Depends on | Size | Status |
| --- | --- | --- | --- | --- |
| 1. Miss breakdown in the scorecard export | Data | none | M | To do |
| 2. "How we miss" on the site | UI | contract below (data from 1) | M | To do |
| 3. Eleven-season miss report | Offline analysis | none | M | To do |
| 4. Preview and full-time cards | UI | 1 for the verdict line (can start without) | L | To do |

Tasks 1, 3 and 4 can start together. Task 2 builds against the contract and merges after Task 1.

**Rules:** those of the [feature plan](feature-plan-2026-10-14.md) apply: the site data contract, schema and validator for new fields; no new top-level tab; existing components; published and reconstructed forecasts labelled; coverage stated where partial; every graphic with a text equivalent; checks at 375 px. No forecast, default or calibration changes.

### Contract

Each scorecard record (`all`, each competition, and their `published` and `reconstructed` cohorts) gains:

```json
"misses": {
  "confusion": [[106, 52, 38], [0, 0, 0], [30, 24, 51]],
  "outcomes": {"expected": [129.8, 74.3, 96.9], "actual": [136, 76, 89]},
  "kinds": {"called": {"won": 0, "level": 0, "lost": 0, "unknown": 0},
            "draw": {"won": 37, "level": 0, "lost": 38, "unknown": 0},
            "upset": {"won": 34, "level": 0, "lost": 34, "unknown": 0}},
  "goals": {"team_games": 600, "predicted": 1.41, "goals": 1.54, "xg": 1.69,
            "mae_goals": 0.94, "mae_xg": 0.70},
  "xg_scored": {"n": 300, "model": 0.0, "elo": 0.0, "frequency": 0.0}
}
```

`confusion` rows are the call (home, draw, away) and columns the result. `goals` and `xg_scored` cover only matches with observed xG; `team_games` and `n` say how many. Each finished fixture in `matches/<competition>.json` gains `miss: {"kind": "called|draw|upset", "xg": "won|level|lost|unknown"}`, using the same forecast the scorecard uses (the receipt when published). Values above are illustrative.

### Task 1. Miss breakdown in the scorecard export

- Extend `src/standing_prediction/scorecard.py` and the exporter with the `misses` block and the per-fixture `miss` field, from the same rows the scorecard already scores. Combine cohorts the way `combine_records` does.
- Update `schemas/site/data.schema.json`, `scripts/validate_site_data.py` (the confusion matrix sums to `n`; the kinds sum to the misses; outcome counts reconcile) and `docs/site-data-contract.md`.
- **Done when:** the numbers above reproduce from the published data, an identical rebuild changes nothing, and pytest, validation and the browser check pass.

### Task 2. "How we miss" on the site

- **Model → Track record:** a new "How we miss" block after calibration:
  - the 3×3 called-against-actual table as a ruled `board`, with counts and row shares;
  - a split meter of the misses: draws on the left, upsets on the right, each split by won / level / lost on chances;
  - expected against actual home, draw and away counts;
  - one line on goals: predicted, actual and xG per team-game, and the two errors;
  - xG-scored log loss beside the real log loss, clearly labelled as a diagnostic.
- **Matches → Scorecard:** one compact line, such as "Misses: 76 draws, 68 upsets; half the upsets won on chances", linking to the block.
- **Match page, After mode:** a small verdict tag from `miss` ("Called it", "Drew; we had the better chances", "Upset; they had the better chances").
- Follow the published/reconstructed toggle the scorecard already has, and state the xG coverage.
- **Done when:** it renders for all competitions, the Champions League (no xG) says so, and `check_site.py` covers the block at desktop and 375 px.

### Task 3. Eleven-season miss report

- Use the [forecast-calibration](../packages/forecast-calibration/README.md) dataset: 19,763 matches from 2015/16–2025/26, each forecast before kickoff, with Understat xG. Score the no-odds blend.
- Report everything in the contract, by league and season, with clustered SEs. Then answer:
  - **Draws:** are draw probabilities calibrated by bin, and by how close the two sides are? How often is a draw the most likely outcome, and would calling draws more often ever improve accuracy or log loss?
  - **Goal level:** is the predicted-goals deficit seen this season systematic or seasonal, and does it differ by league?
  - **xG-scored log loss as a selection aid:** does ranking candidate models by it agree with ranking by real log loss on the same matches, and how much does it shrink the noise? Do not use it to tune the production model.
- Put the report in `docs/`, outputs in `out/`. No model changes.
- **Done when:** each question has an answer with its uncertainty; a "no" is a valid answer.

### Task 4. Preview and full-time cards

- **Where:** the match page gets a "Download card" chip in Before and After modes. Cards are drawn client-side on a canvas from data the page already has and saved as PNG: 1080×1350 portrait, plus 1200×675 landscape for X. Wait for `document.fonts.ready` before drawing; crests are local, so the canvas stays untainted.
- **Preview card:** competition and kickoff, crests and names, the three outcome bulbs with percentages, expected goals, the most likely score, and the stakes tag when the game has one.
- **Full-time card:** final score, xG (where known), our pre-match probabilities labelled published or reconstructed, and a verdict line from `miss` ("Called it" / "Drew; we had the better chances" / "Upset; they had the better chances"). Before Task 1 merges, show the score and probabilities without a verdict.
- Follow [DESIGN.md](../DESIGN.md): the scoreboard look, existing tokens and fonts, Floodlight mark and URL in the footer, sources credited (Understat for xG). No new hues.
- No posting to social accounts. The page itself is the card's text equivalent; the button has a clear label.
- **Done when:** both cards render for a league match with xG, a Champions League match and an upcoming match. Files download at both sizes with legible text, and `check_site.py` clicks the chip without errors.
