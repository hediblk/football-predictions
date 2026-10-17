# Europa and Conference League results coverage

Initial ESPN backfill, fetched on 14 October 2026. The collector scanned every date from 1 July 2025 through 14 October 2026, separately for `uefa.europa` and `uefa.europa.conf`. See the [archive rules and columns](../data/results/README.md). Results are stored as received; no aliases, inferred scores or replacement rows were added. This report predates model integration; the [Task A replay](el-ecl-history-evaluation.md) records the later alias audit, current coverage and integration decision.

## Matches per round

League-phase rounds contain 18 games for 36 clubs. Matchday numbers below follow chronological clusters of adjacent kickoff dates (ESPN provides a stage slug, not a matchday number). Knockout counts include both legs, with expected totals of 16 playoffs, 16 round-of-16 games, eight quarterfinals, four semifinals and one final.

| Season | Competition | Round | UTC kickoff dates | Finished matches | Expected |
| :--- | :--- | :--- | :--- | ---: | ---: |
| 2025/26 | ECL | League phase MD1 | 2025-10-02 | 18 | 18 |
| 2025/26 | ECL | League phase MD2 | 2025-10-23, 2025-10-24 | 18 | 18 |
| 2025/26 | ECL | League phase MD3 | 2025-11-06 | 18 | 18 |
| 2025/26 | ECL | League phase MD4 | 2025-11-27 | 18 | 18 |
| 2025/26 | ECL | League phase MD5 | 2025-12-11 | 18 | 18 |
| 2025/26 | ECL | League phase MD6 | 2025-12-18 | 18 | 18 |
| 2025/26 | ECL | knockout-round-playoffs | 2026-02-19, 2026-02-26 | 16 | 16 |
| 2025/26 | ECL | round-of-16 | 2026-03-12, 2026-03-19 | 16 | 16 |
| 2025/26 | ECL | quarterfinals | 2026-04-09, 2026-04-16 | 8 | 8 |
| 2025/26 | ECL | semifinals | 2026-04-30, 2026-05-07 | 4 | 4 |
| 2025/26 | ECL | final | 2026-05-27 | 1 | 1 |
| 2025/26 | EL | League phase MD1 | 2025-09-24, 2025-09-25 | 18 | 18 |
| 2025/26 | EL | League phase MD2 | 2025-10-02 | 18 | 18 |
| 2025/26 | EL | League phase MD3 | 2025-10-23 | 18 | 18 |
| 2025/26 | EL | League phase MD4 | 2025-11-06 | 18 | 18 |
| 2025/26 | EL | League phase MD5 | 2025-11-27 | 18 | 18 |
| 2025/26 | EL | League phase MD6 | 2025-12-11 | 18 | 18 |
| 2025/26 | EL | League phase MD7 | 2026-01-22 | 18 | 18 |
| 2025/26 | EL | League phase MD8 | 2026-01-29 | 18 | 18 |
| 2025/26 | EL | knockout-round-playoffs | 2026-02-19, 2026-02-26 | 16 | 16 |
| 2025/26 | EL | round-of-16 | 2026-03-12, 2026-03-18, 2026-03-19 | 16 | 16 |
| 2025/26 | EL | quarterfinals | 2026-04-08, 2026-04-09, 2026-04-16 | 8 | 8 |
| 2025/26 | EL | semifinals | 2026-04-30, 2026-05-07 | 4 | 4 |
| 2025/26 | EL | final | 2026-05-20 | 1 | 1 |
| 2026/27 | EL | League phase MD1 | 2026-09-16, 2026-09-17 | 18 | 18 |

The scan appended **360 matches**, with **zero failed daily requests** and no malformed completed results or exceptional statuses reported. Both 2025/26 competitions have complete league-phase-to-final counts: EL 189 and ECL 153. For 2026/27, EL MD1 has 18 results; ECL has **zero finished matches through 14 October**. ESPN lists 18 scheduled ECL league-phase games on [15 October](https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.europa.conf/scoreboard?dates=20261015), all excluded. Its 2026 CSV contains only the header, ready for the first finished results.

## Club-name coverage

Names are compared by exact equality after `standing_prediction.utils.normalize_team` on both sides, with no new aliases or fuzzy matching. The reference is the full 327-club `cl_club_ratings.csv` export from the existing Champions League model, generated at `2026-10-13T04:08:40.131580+00:00` (forecast origin `2026-10-13T04:08:33.189466+00:00`, calibration `global-4c0170be18f1`, code fingerprint `818f976548bd909e`). This includes the model’s domestic rating population, rather than only the 36 Champions League entrants or the smaller published Clubs view.

Reference CSV SHA-256: `4e7d9b19f1d4f097314283599bc0b16f9dee2277a8bcf7389d71d53c0fb2cf6a`. It is the local `out/site/cl_club_ratings.csv` artifact from that run; no new model fit was performed for this report.

| Season | Competition | Matches | Distinct ESPN clubs | Matched rated clubs | Matches with both clubs matched |
| :--- | :--- | ---: | ---: | ---: | ---: |
| 2025/26 | ECL | 153 | 36 | 12 | 29 |
| 2025/26 | EL | 189 | 36 | 21 | 79 |
| 2026/27 | ECL | 0 | 0 | 0 | 0 |
| 2026/27 | EL | 18 | 36 | 20 | 6 |

| Competition, both seasons | Distinct ESPN clubs | Matched rated clubs |
| :--- | ---: | ---: |
| EL | 64 | 37 |
| ECL | 36 | 12 |

Unmatched ESPN names below are ordered by total match appearances across the two archived seasons. A name mismatch does not establish that a club is absent from the model: provider aliases must be audited separately before these results can be used.

| Unmatched ESPN name | EL appearances | ECL appearances | Total |
| :--- | ---: | ---: | ---: |
| AZ Alkmaar | 1 | 12 | 13 |
| Ferencvaros | 13 | 0 | 13 |
| Racing Genk | 12 | 0 | 12 |
| Dinamo Zagreb | 11 | 0 | 11 |
| Lech Poznan | 1 | 10 | 11 |
| NK Celje | 1 | 10 | 11 |
| FC Midtjylland | 10 | 0 | 10 |
| Ludogorets Razgrad | 10 | 0 | 10 |
| Red Star Belgrade | 10 | 0 | 10 |
| Rijeka | 0 | 10 | 10 |
| SK Brann | 10 | 0 | 10 |
| Jagiellonia Bialystok | 1 | 8 | 9 |
| Omonia Nicosia | 1 | 8 | 9 |
| RB Salzburg | 9 | 0 | 9 |
| SK Sturm Graz | 9 | 0 | 9 |
| Sparta Prague | 1 | 8 | 9 |
| AEK Larnaca | 0 | 8 | 8 |
| Drita Gjilan | 0 | 8 | 8 |
| FC Basel | 8 | 0 | 8 |
| FC Noah | 0 | 8 | 8 |
| FCSB | 8 | 0 | 8 |
| Feyenoord Rotterdam | 8 | 0 | 8 |
| KF Shkëndija | 0 | 8 | 8 |
| KuPS Kuopio | 0 | 8 | 8 |
| Lausanne Sports | 0 | 8 | 8 |
| Maccabi Tel-Aviv | 8 | 0 | 8 |
| Malmö FF | 8 | 0 | 8 |
| Raków Czestochowa | 0 | 8 | 8 |
| Young Boys | 8 | 0 | 8 |
| Zrinjski Mostar | 0 | 8 | 8 |
| BK Häcken | 0 | 6 | 6 |
| Breidablik | 0 | 6 | 6 |
| CSU Craiova | 0 | 6 | 6 |
| Hamrun Spartans | 0 | 6 | 6 |
| Legia Warsaw | 0 | 6 | 6 |
| Lincoln Red Imps | 0 | 6 | 6 |
| Rapid Vienna | 0 | 6 | 6 |
| Shamrock Rovers | 0 | 6 | 6 |
| Shelbourne | 0 | 6 | 6 |
| Ararat-Armenia | 1 | 0 | 1 |
| Hapoel Be'er | 1 | 0 | 1 |
| Levski Sofia | 1 | 0 | 1 |
| NEC Nijmegen | 1 | 0 | 1 |
| Olympiacos | 1 | 0 | 1 |
| Torreense | 1 | 0 | 1 |

## Limits and validation

The backfill has no historical publication timestamps. `fetched_at` records the new observation in October 2026, and a historical replay would need a documented result-availability approximation. Extra-time scores are preserved and must not silently be used as 90-minute results. Archived corrections are never overwritten.

The existing offline suite passed (124 tests); the published dataset validator checked 323 files and the browser check loaded 36 views without errors. Archive checks cover unique ESPN IDs, season placement, UTC timestamps, nonnegative integer scores, allowed statuses, shootout winners and an unchanged archive on a repeated date fetch.
