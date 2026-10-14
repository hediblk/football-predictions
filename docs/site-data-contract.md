# Published site data contract

Implemented by the shared [JSON schema](../schemas/site/data.schema.json), [validator](../scripts/validate_site_data.py), and [exporter/contract tests](../tests/test_site_contract.py). [ADR 0001](adr/0001-site-model-boundary.md) records the boundary decision and [ADR 0002](adr/0002-site-browser-checks.md) the browser checks. [Numerical protection](numerical-protection.md) covers forecasting behavior before export.

Run `python scripts/validate_site_data.py --data site/data` to validate the current site. For a staged dataset, pass `--data <candidate-directory> --site site` so crest references resolve against the real site assets. Failures exit nonzero and identify the affected file or field. Run the focused tests with `PYTHONDONTWRITEBYTECODE=1 python -m pytest -q tests/test_site_contract.py tests/test_refresh_site.py`.

## Boundary and guarantees

`scripts/build_site_data.py` converts model outputs to the JSON consumed by the static site. Validate this conversion independently of model tests: a correct model can still be exported with a missing field, reversed tuple, incorrect unit, or inconsistent index. Validate the complete final dataset again before publication, including retained files and historical seasons.

Machine-readable schemas should be the authority for required fields, types, nullability, and tuple shapes. This document is the authority for football meanings, units, consistency rules, and compatibility policy. Use a small shared validator for relationships schemas cannot express. A new JSON family needs an explicit schema mapping before publication; avoid one schema copied for every competition.

Contract validation guarantees that published data conforms to these rules. It cannot guarantee JavaScript imports, rendering, interactions, or layout; the [browser checks](adr/0002-site-browser-checks.md) load every view from the same data, and layout still receives manual review.

## File families

| Path | Structure and required meaning |
| --- | --- |
| `index.json` | Nonempty competition array, currently six distinct slugs. Entries contain `slug, code, name, country, season, generated_at`, matching the corresponding published competition file. Index order is not a display-order contract. |
| `<competition>.json`, domestic | Common metadata; `kind: league`; zones and nonempty teams. Each team has identity, current position/played/points/goal difference, expected final points/position, point quantiles, position probabilities, title chance, and declared zone chances. Fixture-adjustment notes may be absent in older data. |
| `champions-league.json` | Common metadata; `kind: ucl`; 36 teams with canonical `key`, league-phase position probabilities, `r16, playoff, out`, progression `stages`, and the representative `bracket`. |
| `matches/<competition>.json` | `slug, generated_at, rule, matches`. `rule` can be null. Fixtures carry `id, kickoff, status, md, home, away, home_id, away_id`, with conditional scores, forecasts, xG, and stakes. A present UCL fixture file must not have an empty list: its round view requires fixtures. |
| `clubs.json` | `generated_at, season, scale, league_averages, featured, clubs`; nonempty ranked clubs with identity, domestic league, UCL participation, ratings, expected goals against the reference opponent, and overall/attack/defense/domestic ranks. Champions League clubs from outside the five leagues have a null `league` and `league_rank`, with `country` and a three-letter `country_code`. |
| `crests.json` | Object keyed by decimal-string provider IDs. Entries contain `name, source, path`, with dimensions for PNGs. Published crest paths refer to local site assets. A missing crest entry leaves the club name usable. |
| `history/<season>/<competition>.json` | `slug, season, metrics, dates, cutoff, teams`. Each team has one series per metric, with entries aligned to `dates`. Domestic metrics are `title,ucl,releg`; UCL metrics are `top8,top24,last16,qf,sf,final,title`. |
| `history/<season>/clubs.json` | `season, fields, weeks`; each week has a Monday `date`, nullable result `cutoff`, and club-ID-string keys mapped to rating tuples. `fields` is currently `rating,attack,defense`. |
| `history/<season>/forecasts/<competition>.json` | `slug, season, fixtures`, keyed by positive decimal-string fixture IDs. Receipts contain `kickoff, generated_at, p, exp, top, call, btts, o25` and optional `stakes`, copied at published precision. Missing files or receipts mean no published forecast was saved. |
| `match/<season>/<competition>/<fixture id>.json` | Per-match detail, loaded on demand by future match-page sections. Required envelope: `id, competition, kickoff, sources`; `competition` is the route slug and the season directory is its start year. `shots, players, retro` are optional; missing files or keys mean that source is unavailable. The family also accepts later ESPN/UEFA additions. |

Common competition metadata is `slug, kind, code, name, country, season, generated_at, as_of, data_cutoff, n_sim, played_fixtures, remaining_fixtures`. Zone entries contain `key, label, from, to`, with inclusive one-based position bounds.

Required current competition tables, index, and club rankings must exist and be nonempty. Match files, histories, and crests have existing missing-data fallbacks; absence is allowed where that fallback applies. A present file must be well-formed: optional availability is not permission to publish malformed JSON. Historical files can be empty during initialization where their consumers allow it.

## Units, ordering, and field meanings

| Field | Meaning and unit |
| --- | --- |
| Team `probs[i]` | Chance of finishing in position `i + 1`, percent on 0–100 scale |
| Team `position` | Current table position; separate from the projected ordering of `teams` |
| Domestic `title, ucl, europe, releg` | Chances of finishing in their declared positions, percent; these are position bands, not guaranteed sporting qualification/relegation |
| UCL `r16` | Top-eight league-phase finish and direct entry to the last 16, percent |
| UCL `playoff, out` | League-phase places 9–24 and 25–36 respectively, percent |
| UCL `stages.round16` | Reaches the last 16, including playoff winners, percent |
| Other UCL stages, `title`, bracket `advance` | Progression/winner chances, percent; bracket advancement covers the entire tie |
| Match `p` | `[home win, draw, away win]`, each on 0–1 scale |
| Match `score, xg, exp` | `[home, away]` goals, observed xG, or expected goals respectively |
| Match `top` / `call` | Tuples `[home goals, away goals, probability]`, probability on 0–1 scale; `top` ordered by descending probability |
| Match `btts, o25, p_score` | Both-teams-score, over-2.5-goals, and observed-score probabilities on 0–1 scale |
| Stakes `n` and each metric array | `[match home win, draw, match away win]`; `n` is simulation counts and metric entries are percentages or null. Domestic metrics are `title, ucl, releg` (as in the table); UCL metrics are `top8, top24` (league-phase places 1–8 and 1–24) and `title` (wins the trophy) |
| Club rating fields | `rating, attack, defense, home, away, league_rating` on a 0–100 expected-points-share scale; these are not title chances |
| Club `gf, ga` | Expected goals against the reference opponent |
| Weekly club tuple | Rating values in `fields` order, currently `[rating, attack, defense]` |
| Fixture-note `score` | Human-readable string or null, unlike a match's integer score pair |
| Match-detail `sources.understat` | `{id, fetched_at}`: positive integer Understat match ID and timezone-qualified retrieval timestamp |
| Match-detail `shots` | Tuples `[minute, side, x, y, xg, result, situation, body, player, assister]`, ordered by minute. `side` is `h` or `a`; minutes are Understat's zero-based elapsed minutes, including stoppage time. Coordinates are Understat's unmodified 0–1 pitch fractions, with `x` toward the attacking goal and `y` across the pitch. Shot xG is on 0–1; result/situation/body retain provider labels; player/assister are names, with null for no assister. |
| Match-detail `players` | `{h, a}` arrays of rows: `id` (Understat player ID), `player` (name), `minutes, position, shots, goals, own_goals, xg, xa, key_passes, yellow, red`. Goals exclude own goals; own goals count against the player's side. `xg` and `xa` are observed expected goals/assists, not pre-match model rates. Cards are counts. |
| Match-detail `retro` | `[home win, draw, away win]`, on 0–1. After-the-fact chances from the exact convolution of independent Bernoulli trials with each side's observed shot xGs. This assumes shots are independent, including successive attempts in the same attack; own goals are excluded. These are not pre-match forecasts and never feed the model. |

Stakes always use the fixture's home/draw/away order, including for affected clubs that are not playing in that fixture. Null means insufficient conditioning simulations, not zero chance. UCL match scores and match forecasts cover 90 minutes; tournament progression also accounts for the remainder of a tie.

The representative UCL bracket is illustrative. Its champion need not have the largest unconditional title probability. `call` is a score within the most likely outcome; it need not equal `top[0]` or appear among the listed `top` scores. The listed top score probabilities are a subset and must not be required to sum to one.

## Missing values, identifiers, and time

- Provider club IDs in tables, clubs, and match sides can be positive integers or null. Nonnull team IDs are unique within each table or club ranking, and fixture `id` values are unique within each match file. Club `home_id`/`away_id` values naturally repeat across fixtures, and the same club appearing in domestic and UCL tables is expected. Route slugs must be unique in their routing scope.
- Competition history uses a numeric club ID, or the club slug when the ID is unavailable. Weekly club history contains numeric provider IDs serialized as object keys. Preserve these identity rules rather than treating names as stable keys.
- Match `md`, domestic `data_cutoff`, history cutoffs, and history series entries can be null. Preserve null instead of substituting zero or an empty string.
- Predictions can be absent. If `p` exists, require its full companion group: `exp, top, btts, o25, at`. `call` supports older optional data; `p_score` applies when an observed score is available. `xg, reported, stage, neutral, stakes` are conditional fields.
- Optional match `published` is a boolean. Finished fixtures with `published: true` use the receipt's forecast fields and its run `generated_at` as `at`; fixtures without a receipt retain reconstructed forecasts and omit the flag. For published fixtures, `p_score` is included only when the actual score occurs in the saved `top` or `call`; it never comes from a reconstructed forecast.
- A `FINISHED` fixture requires an integer home/away score pair. Forecast fields on finished fixtures describe the prior forecast, not a post-result prediction. Unknown provider status strings are not automatically malformed; retain existing status interpretation.
- Parse timestamps with an explicit timezone and dates as calendar dates. `generated_at`, forecast origin `as_of`, and result `data_cutoff` are distinct. Match-file `generated_at` currently represents forecast origin; table generation time represents execution time.
- Domestic result cutoff covers current-season completed results. UCL cutoff covers training results across leagues, and its exporter substitutes `as_of` when a result cutoff is unavailable.
- Do not require every forecast time to precede kickoff: an unplayed postponed/cancelled fixture can retain an old kickoff while receiving a new forecast. Pre-match timing protection belongs to completed-match forecast tests.
- Receipt `generated_at` is the competition run's execution timestamp, distinct from the match-file forecast origin. It must strictly precede the saved kickoff. Only fresh competition exports save receipts, for unplayed fixtures with a forecast whose kickoff is after both the run and the build time. Before kickoff a receipt can be replaced; after its saved kickoff it is immutable, even if a later feed reschedules the fixture. Retained competitions write nothing. There is no historical backfill.
- Domestic model `*_match_forecasts.json` and match snapshots carry optional `understat_id` from the existing score/kickoff-checked xG join. It is an internal provider identifier, omitted from published `matches/<competition>.json` and all probability calculations. Shot ingestion reads it from fresh model outputs and checks against the staged published fixture.

## Consistency checks

Reject nonfinite numbers, malformed required dates, wrong tuple lengths, duplicate scoped identities, invalid route references, nonpositive/noninteger simulation counts, negative fixture/played counts, and out-of-range probabilities or ratings. Scores are nonnegative integers. Points and goal difference can be signed because deductions and losing records are valid; do not impose nonnegative expected points or point quantiles universally.

Within each competition:

- Position-probability vector length equals team count; current positions form the appropriate table permutation. Each position-matrix row and column sums to 100% within export-rounding bounds.
- Domestic title chance matches the first position, and zone chances match their inclusive position slices. Expected position matches the weighted position probabilities within its separate rounding bound. Require `p10 <= p90`; the mean need not lie inside that interval.
- UCL `r16 + playoff + out` sums to 100%. Top-eight, playoff, and eliminated totals conserve 8/16/12 places; round-of-16, quarterfinal, semifinal, final, and title totals conserve 16/8/4/2/1 places. Progression is nested and top-eight probability does not exceed last-16 probability.
- Bracket tie participants are valid UCL teams, the winner is one of its participants, and the champion matches the final winner. Validate advancement range and tuple identities without pretending the illustrative bracket is the only possible draw.

Within matches and history:

- Match outcome triples sum to one; a present `top` is nonempty, finite, and sorted by probability. Pair/tuple lengths and units are fixed. Stakes counts are nonnegative integer triples; metric triples preserve nulls and known percentage ranges.
- Receipts obey the same forecast probability, scoreline and stakes checks. Published finished fixtures must have a forecast with `at` strictly before kickoff. Receipt filenames and season directories must agree with their `slug` and `season`.
- History dates strictly increase and each metric series has exactly `len(dates)` entries. Week dates strictly increase and represent Mondays; missing days and weeks are valid. The history season's start year matches its directory (`2026/27` → `history/2026/`), while older-season members may differ from today's clubs.
- Published club ranking numbers form the relevant rank sequences; overall list order agrees with overall rank. Featured IDs reference available ranked clubs. Crest paths, where declared, resolve to the published assets.
- Match-detail IDs and competition slugs agree with their paths; retrospective chances sum to one, player IDs are unique within each side, and Understat retrieval is after kickoff. Current-season files must match a finished published fixture with the same ID and kickoff. At ingestion, each side's shot xG sum must be at least its published match `xg` minus 0.05, and `Goal` shots plus opposition players' own goals must equal the final score. The sum may exceed the match figure, because Understat's match xG counts shots from the same attack as one chance (1 − ∏(1 − xG)). Later dataset validation repeats only the identity and status checks, so a provider revision or a corrected result after publication cannot block a refresh. Older season files remain valid without today's fixture list.

Across files, each index entry agrees with its table's identity and generation metadata. Nonnull club league slugs and required file references resolve. Do not require universal membership or equal timestamps/seasons between independently retained tables, matches, ratings, and history. `scale.clubs` describes the model's reference population, not the length of the published clubs array; the ranking holds the five leagues' clubs and the current UCL field, and weekly history can hold clubs that have since left both.

## Rounding budgets

Use tolerances derived from serialization precision, separate from numerical regression tolerances. Never use a relative tolerance that grows with the magnitude of an invalid percentage.

For `m` values independently rounded to `d` decimal places, their sum has an error budget of `m × 0.5 × 10^-d`, plus a small explicit floating-point allowance. When comparing two rounded quantities, include the rounding contribution from both sides.

- Match `p` values have four decimals: use `0.0002` absolute tolerance for the triple's sum to one.
- Table probability cells have two decimals: a row or column with `N` values has a sum budget of `N × 0.005` percentage points, plus any documented precision lost in intermediate model files.
- Comparing a rounded zone value to `m` rounded position cells needs `(m + 1) × 0.005` percentage points, plus any intermediate-file rounding.
- Expected position weights cell errors by position: its bound is `0.005 × sum(1..N) / 100 + 0.005` places, plus documented intermediate rounding. The final term allows the displayed expected position's own rounding.
- Historical chances and stakes use one decimal below 10% and whole percentages at/above 10%. Do not enforce aggregate probability sums or exact agreement with today's two-decimal table on those series.

Document any extra allowance for upstream CSV precision. Keep range checks strict for directly rounded probabilities; allow rounding bounds when checking derived sums or relationships rather than making every numeric field broadly permissive.

## Validation and publication

Run exporter tests on frozen model outputs and validate their generated JSON. Include deliberately invalid examples: missing required fields, a 0–100 match probability triple, wrong tuple lengths, NaN, duplicate IDs, a broken index reference, and a history series of the wrong length. Include valid examples with null IDs, absent optional forecasts/history/crests, point deductions, and retained older competition files.

Exporter tests must also compare known input/output meanings, including tuple order and units. Swapping valid home/away probabilities can preserve types, ranges, and the sum; a schema cannot infer that semantic mistake from the JSON alone. Known fixture expectations provide that protection.

During refresh, assemble fresh exports and retained files into a candidate dataset, then validate the entire candidate before committing or deploying it. At least one successful forecast remains necessary for a successful refresh; all-six failure keeps the existing failure behavior. Invalid candidates fail publication and leave the deployed site in place. Do not mark retained data as freshly generated or add history points from a failed forecast.

Site-only publication validates the data shipped with that revision. Deploy the exact immutable artifact that passed validation: a later checkout of moving `main` is a different candidate and needs validation again. Daily bot commits do not trigger other workflows, so refresh must invoke the same gate explicitly. No provider access is needed for PR checks or data validation.

Old but valid data is not structurally invalid. Treat freshness separately from schema validity; the current global updated indicator uses the newest competition and can conceal an older retained competition.

`scripts/fetch_match_events.py` runs after exports and before candidate validation in `refresh_site.sh`. It fills finished domestic fixtures with joined Understat IDs on the next refresh, including the existing season's games. Successful derived Understat data is never refetched or replaced; files from another source keep their keys when Understat is added. Raw payloads and failed-attempt markers live in uncommitted `.cache/understat/matches/`. Requests are at least one second apart, with one attempt per fixture per run. A first attempt is allowed for older games; subsequent failed attempts retry only through seven days after kickoff. Fetch, missing-data and consistency failures log warnings and publish no Understat data; they never fail a forecast refresh. Retained competitions without fresh model outputs are skipped.

## Compatibility and changes

Allow additive fields so compatible exporter additions do not force a site update. Removing a consumed field, changing its meaning/unit, changing tuple order, tightening nullability, or changing a required shape is a breaking change even if the JSON still parses.

A breaking change must update schemas, exporter, affected consumers, fixtures, and documentation in the same review. Migrate retained data and older histories or provide a deliberate compatibility path; relying on the next successful model refresh leaves old files exposed. Start with one current contract rather than maintaining several parallel versions.

Passing this gate means data is valid under this contract. The browser checks then show that every view renders from it without script errors; neither proves the numbers are right.
