# Historical EA ratings and Understat identities

`vintages.json` catalogs men's Career Mode ratings from FIFA 15 through FC 26, one edition for each season starting in 2014–2025. Raw ZIPs and compact per-vintage CSVs stay in the ignored player cache. No site, refresh or forecast code consumes these files.

The build links **32,541 / 33,451** club-season players. It covers **42,277,086 / 42,624,916 archived minutes (99.18%)** by identity, and **39,469,691 minutes (92.60%)** with a same-season rating available before kickoff. One EA ID is one player, so birth dates that differ across vintages by up to 400 days (a day's timezone drift, swapped day and month, 1 January placeholders later corrected) do not block a link. The 910 unresolved rows include 857 without a club/name match, 40 EA IDs whose birth dates differ by more than 400 days, 11 duplicate Understat identities for an EA ID and two ambiguous name matches. They remain in the table with reasons.

## Sources and dates

| Edition | Vintages | First snapshot | Last snapshot | Retained player records |
| --- | ---: | --- | --- | ---: |
| FIFA 15 | 59 | 2014-08-29 | 2015-09-10 | 962,549 |
| FIFA 16 | 58 | 2015-08-28 | 2016-09-22 | 986,175 |
| FIFA 17 | 91 | 2016-08-25 | 2017-08-24 | 1,601,431 |
| FIFA 18 | 84 | 2017-08-28 | 2018-09-12 | 1,512,360 |
| FIFA 19 | 68 | 2018-07-19 | 2019-06-24 | 1,229,986 |
| FIFA 20 | 61 | 2019-08-20 | 2020-09-23 | 1,128,336 |
| FIFA 21 | 64 | 2020-08-24 | 2021-09-25 | 1,197,628 |
| FIFA 22 | 64 | 2021-08-16 | 2022-07-18 | 1,218,451 |
| FIFA 23 | 9 | 2022-09-01 | 2023-01-13 | 166,674 |
| FC 24 | 1 | 2023-09-22 | 2023-09-22 | 18,350 |
| FC 25 | 2 | publication bound: 2024-09-26 | 2025-06-03 | 34,327 |
| FC 26 | 1 | 2025-09-19 | 2025-09-19 | 18,405 |


| Source | Edition(s) | Pinned dataset version | Raw filename under `research/` |
| --- | --- | ---: | --- |
| [Stefano Leone, FIFA 23 complete player dataset](https://www.kaggle.com/datasets/stefanoleone992/fifa-23-complete-player-dataset) | FIFA 15–23, including dated updates | 1 | `fifa-23-complete-player-dataset.zip` |
| [Stefano Leone, FC 24 complete player dataset](https://www.kaggle.com/datasets/stefanoleone992/ea-sports-fc-24-complete-player-dataset) | FC 24 | 4 | `ea-sports-fc-24-complete-player-dataset.zip` |
| [Davis Nyagami, FC 25 database](https://www.kaggle.com/datasets/nyagami/ea-sports-fc-25-database-ratings-and-stats) | FC 25, September EA export | 5 | `fc25-launch.zip` |
| [Aniss7, FC 25 SoFIFA export](https://www.kaggle.com/datasets/aniss7/fifa-player-data-from-sofifa-2025-06-03) | FC 25, 3 June 2025 update | 1 | `fifa-player-data-from-sofifa-2025-06-03.zip` |
| [rovnez, FC 26 player data](https://www.kaggle.com/datasets/rovnez/fc-26-fifa-26-player-data) | FC 26, 19 September 2025 update | 3 | `fc-26-fifa-26-player-data.zip` |

The source dataset pages and their metadata were checked on 16 October 2026 UTC. The public Kaggle API downloads worked without an account. If that changes, download the pinned versions linked by `download_url` in the manifest, and put the ZIPs under `/Users/hedibelkahia/codes/football/.cache/players/research/` with the filenames above. Never supply credentials to these scripts. FIFA 15–23 also has a [public Hugging Face mirror](https://huggingface.co/datasets/jsulz/FIFA23), but the acquired ZIP is the Kaggle original.

These sources describe EA ratings scraped from SoFIFA, except Nyagami's export, whose publisher links an EA website scraper. Publisher provenance and snapshot dates are claims, not independently archived proof of historical publication. The manifest records those claims explicitly. The FC 24 file actually contains annual snapshots, despite its broader dataset description; only its FC 24 rows are imported, avoiding overlap with the full FIFA 15–23 history. No complete in-season history is claimed for FC 24–26. Older FC 26 dataset versions 1 and 2 returned HTTP 404, so no dates or rows are invented for them.

SoFIFA's `fifa_update_date` (FC 24's `update_as_of`, June FC 25's `version`) supplies `snapshot_date`. FC 26's member is named `FC26_20250921.csv`, but its row-level update date is **2025-09-19**. The September FC 25 export has no snapshot date or birth dates: `snapshot_date` stays null and its dataset publication timestamp, **2024-09-26T08:14:25.953Z**, is a conservative availability upper bound, not an asserted EA release date. Date-only snapshots become eligible at the next UTC midnight; timestamped publication bounds retain their precision.

The manifest's `sources` entries pin a source page, dataset version, download URL, raw ZIP filename, member and SHA-256. Each `vintages` entry records edition, season start year, source update identifier, snapshot/availability dates and their basis, compact filename, row count, birth-date count and SHA-256. `source_rows` counts source rows for that vintage; `duplicate_rows_removed` counts identical compact records collapsed before export. Conflicting duplicate EA IDs fail. The June FC 25 export has 39 identical compact repeats. Raw ZIP bytes remain unchanged. Hashes of compact files refer to UTF-8 CSVs sorted by EA ID, with LF endings and columns `ea_id,name,short_name,dob,club,overall,positions`; they are not hashes of the ZIP or its original member.

The supplied research copies were inspected. `fc26_sofifa.csv` agrees with the dated rovnez file on IDs, names, clubs, birth dates, positions and overall, but omits the date columns; the dated original is used instead. `fc26_hf.csv` has IDs/birth dates but no recoverable snapshot date/source in the file. `fc26_ea.csv` has neither EA IDs nor birth dates, and `ea-live-sample.json` is only a live sample. These are not assigned historical dates. `fc27_ea.csv` is outside this task's edition range and is not used.

## Reproduce

**Builders removed from `main` (24 October 2026).** These files fed only the EA prior experiment, which was not adopted, so the archived data and this README stay. The scripts are at commit `bb6a1b7`: [`build_ea_vintages.py`](https://github.com/hediblk/football-predictions/blob/bb6a1b7/scripts/build_ea_vintages.py) and [`link_understat_ea.py`](https://github.com/hediblk/football-predictions/blob/bb6a1b7/scripts/link_understat_ea.py). Check out that commit to run the commands below.

Run from the repository root with the existing environment. The default cache is this checkout's `.cache/players`; use the main checkout's cache in a worktree:

```bash
PYTHONDONTWRITEBYTECODE=1 python scripts/build_ea_vintages.py \
  --cache /Users/hedibelkahia/codes/football/.cache/players --download
PYTHONDONTWRITEBYTECODE=1 python scripts/link_understat_ea.py \
  --cache /Users/hedibelkahia/codes/football/.cache/players
```

Omit `--download` for a wholly offline rebuild. It only downloads missing ZIPs, at least one second apart; it does not refresh existing sources. Once a manifest exists, different raw bytes fail its source hash check. The linker checks every compact vintage's hash and row count before matching. Identical inputs preserve output bytes and modification times. The report, coverage CSV, input hashes and 30 sampled rows go to `out/ea-links/`, with seed **20261016** for the sample. The PR includes the full 60-cohort coverage table and the 30 checks.

## Link table and coverage

[`../understat_ea_links.csv`](../understat_ea_links.csv) has one row per `(league, season, team, understat_id)`. `understat_names` preserves all observed spellings; `minutes` sums that cohort's archived appearances. `ea_id` belongs to EA's namespace. Provider numeric IDs are never compared. Unmatched/ambiguous rows retain their names, minutes, reason and candidate IDs, with blank EA identity/method/confidence fields.

Names are matched within the vintage's club and season using the existing accent/punctuation normalization, exact names, multi-token subsets, established given-name variants and unique single names. HTML entities, apostrophes and Latin letters not decomposed by Unicode normalization (for example Icelandic ð/þ) are normalized explicitly. As a weaker fallback, an initialled EA name such as `M. Hasebe` can match `Makoto Hasebe` when the surname tokens agree exactly and the given initial agrees; the candidate must still be unique within the club-season and pass the career checks. This also handles EA full names published only in native script, without inventing a transliteration. Historical licensed-name aliases (Piemonte Calcio/Juventus, Latium/Lazio, Bergamo Calcio/Atalanta, Roma FC/Roma, Milano FC/Milan, Lombardia FC/Inter, Napoli FC/Napoli) are confined to this script. The [EA Serie A announcement](https://www.ea.com/ea-play/news/ea-sports-serie-a-exclusive-partnership-announcement) lists the older unlicensed names; the [FC 25 team database](https://www.fifacm.com/25/league/31/italy-serie-a-1) and the source player rosters distinguish Milano/Milan from Lombardia/Inter. No current squad or current identity override is used.

Every unique club-name match contributes a career candidate. One Understat ID must resolve to one EA ID across all seasons; a second EA ID quarantines the entire career. Multiple Understat IDs resolving to one EA ID are also quarantined. All nonempty EA birth dates for the selected ID must agree across vintages; contradictions remain ambiguous. **Understat supplies no birth dates**, so EA's date is a consistency check, never a claimed birth-date match between providers. A career established in another club-season can fill an unresolved cohort only when its local candidates do not contradict it. Such rows use `career_consistency`; their `ea_club` and `evidence_vintage` describe the supporting anchor, not necessarily that season's membership.

`exact_name_club` has qualitative `high` confidence; `name_tokens_club`, `single_name_club`, `initial_surname_club` and `career_consistency` have `medium` confidence. These are review categories, not calibrated probabilities. `evidence_vintage`, `ea_name`, `ea_dob` and `ea_club` make the chosen evidence inspectable. `ea_dob` is blank when the evidence vintage lacks it, even if another vintage supplies a consistent birth date for the career check. A link is a retrospective identity hypothesis, not proof of registration or contemporary availability. Unknown stays unresolved rather than becoming a guessed ID.

Coverage uses the sum of **archived player appearance minutes**, separately for each of the 60 league-seasons. Excluded Understat games have no appearance rows and are outside that denominator; see [the archive's exclusions](../understat/README.md). Identity coverage counts matched rows. Dated-rating coverage additionally requires that EA ID to have a valid overall in that season's edition with `available_from` strictly before the match kickoff. The earliest eligible vintage establishes whether a rating exists; a future model must select the latest eligible vintage, never the latest edition-wide row. No older-edition fallback is counted, and a later career confirmation never backdates a rating. In particular, August/early-September matches often precede an edition's first snapshot. Report percentages are not claims about a historical holdout or live forecasting performance.
