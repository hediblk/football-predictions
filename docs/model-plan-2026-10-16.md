# Model plan, 16 October 2026

Two model tasks that serve the [roadmap](../ROADMAP.md) goals: good Champions League forecasts, and good league-winner odds judged on match log loss. Each is one agent session and one pull request. Player-level forecasting is on hold: [Task 8](expected-xi-forecast-adjustment.md) found no match-probability gain from lineups, even with the actual starters.

| Task | Area | Depends on | Size | Status |
| --- | --- | --- | --- | --- |
| A. Europa and Conference League results as cross-league evidence | Champions League | none | L | To do |
| B. Non-penalty xG with a team penalty rate | Domestic model | none | M | [PR #62](https://github.com/hediblk/football-predictions/pull/62) |

The tasks touch different packages and can run in parallel.

## Rules for both tasks

- Read `AGENTS.md`, `README.md`, `CONTEXT.md`, `PLAN.md`, the [numerical protection guide](numerical-protection.md) and the relevant package README first. Do not edit `deferred-notes/`.
- **No leakage.** Every result, xG value and price must be available before the forecast origin. Where availability is approximated, record the approximation.
- **Judge on match log loss**, with Brier/RPS alongside and clustered standard errors. Use fixed seeds and identical fixtures and origins for every variant. Report coverage and exclusions.
- **Earlier-only choices.** Any setting chosen from results is chosen on earlier seasons and checked unchanged on later ones. State when a design decision was made after seeing the seasons it is judged on.
- **No silent recalibration.** Neither task replaces `calibrated_weights.json` or changes published forecasts on its own. A positive result is proposed as a separate, explicit calibration or integration change.
- Python: no docstrings or new tests unless asked; `PYTHONDONTWRITEBYTECODE=1`; delete any `__pycache__`. Outputs go in `out/`; the report goes in `docs/`. Set this table's status to the PR link.

## Task A. Europa and Conference League results as cross-league evidence

**Why:** league offsets decide how a Premier League side compares with a Portuguese or Dutch one. The Europa and Conference Leagues are where mid-table clubs from different leagues meet. The joint model already uses them, but only for 2024/25, from openfootball. The [ESPN archive](../data/results/README.md) has complete 2025/26 results and is appended daily for 2026/27. The 10 December market-weight recheck needs this evidence.

**Data:**

- Add `data/results/<season>/{EL,ECL}.csv` to the joint fit's European history for 2025/26 onward, next to the openfootball 2024/25 supplement. Never use two sources for the same match.
- **Identities.** [Coverage](el-ecl-results-coverage.md) shows only 37 of 64 Europa League and 12 of 36 Conference League ESPN names matching rated clubs exactly. Add source-backed ESPN aliases in `identities.py`, as was done for The Odds API's names. A club whose domestic league the model does not cover cannot be placed on the scale; exclude matches involving such clubs, and count the exclusions by reason.
- **Scores.** ESPN scores include extra time. Keep 90-minute results only: exclude `after extra time` and `penalties` rows from the goals likelihood and count them. Two-legged ties stay as two matches.
- **Availability.** `fetched_at` is the backfill time, not when the result was known. Treat a result as available three hours after kickoff, and record this approximation in the metadata.
- Optionally backfill ESPN for 2023/24 and 2024/25 with `scripts/archive_results.py` to check that ESPN and openfootball agree on 2024/25. Keep openfootball as the 2024/25 source unless they disagree.

**Evaluation (`football-ucl --evaluate`):**

- Replay 2024/25 and 2025/26 at the existing origins with three variants: without any EL/ECL results, with openfootball 2024/25 only (today's model), and with both sources.
- Report international match log loss on Champions League matches. Also score Europa and Conference League matches between covered clubs, which test cross-league levels directly. Add stage Brier and position RPS.
- Show the league offsets for each variant at the latest origin, especially Serie A (currently last of the big five at 57.5, against StatsUltra's 69.8) and the Premier League lead.

**Integration:** if the full-history variant is no worse on Champions League log loss in both seasons and improves cross-league matches, the PR may make it the default. Include the before/after offsets and the change to today's Champions League forecast in the PR body. Otherwise keep it behind a flag and report why. The archived Europa and Conference League prices stay for the 10 December recheck.

**Done when:** the replay table and offsets are in the report, exclusions are counted, and `scripts/validate_site_data.py` and the existing tests pass.

## Task B. Non-penalty xG with a team penalty rate

**Why:** penalties put about 0.76 xG on one shot, so a few awarded penalties can move a team's xG strength more than its open play deserves. Dropping penalties entirely would discard a real team trait: some teams win more of them. The [roadmap](../ROADMAP.md) parks this as cheap to test, since npxG is already in the cached Understat responses.

**Data:** Understat's `getLeagueData` responses, already cached for 2014/15 onward, carry `npxG` and `npxGA` per team-match in `teams[*].history`. Join them to `dates` by team and kickoff without changing the default output of `fetch_understat_matches`. Team-game penalty xG is `xG − npxG`. Check that every join is one-to-one and that `xG` agrees with the `dates` values; count mismatches.

**Variants, all through the existing xG strength fit and blend:**

1. **xG** (today's model).
2. **npxG:** non-penalty xG for and against replaces xG in `fit_xg_strengths`.
3. **npxG + team penalty rate:** npxG strengths, plus each team's penalty xG for and against as a separate, strongly shrunk team rate: a time-decayed mean shrunk to the league mean, with shrinkage chosen on earlier seasons. Add the expected penalty xG back to each side's xG rate before blending.

**Evaluation:** use the [forecast-calibration](../packages/forecast-calibration/README.md) protocol: the same leagues, 2015/16–2025/26, origins and holdout. For each variant, refit the xG weight and scale on the training seasons, then compare no-odds match log loss, Brier and RPS on the held-out seasons, by league and season, with paired clustered SEs. The Elo-K change parked at 0.0005 log loss is the yardstick for "worth it". Add title and top-four log loss from season replays as checks.

**Integration:** none in this PR. If a variant wins on the held-out seasons, propose a separate calibration PR that rebuilds `calibrated_weights.json` with it.

**Done when:** the report states whether either variant beats today's xG on held-out log loss, with coverage and join checks.
