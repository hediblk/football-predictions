# Understat historical match sheets

Player appearances and team-game xG from [Understat](https://understat.com/), five domestic leagues, 2014/15–2025/26. League names follow the provider (`EPL`, `La_liga`, `Bundesliga`, `Serie_A`, `Ligue_1`); season filenames use the start year. Only finished games in the cached `getLeagueData/<league>/<season>` listings are requested. The coverage denominator is those listings, not an assumed 380 fixtures: Ligue 1's shortened 2019/20 season and its later 18-club seasons have fewer games.

## Source and reproduction

`scripts/fetch_understat_rosters.py` fetches `https://understat.com/getMatchData/<id>` using the existing browser/AJAX headers, with at least one second between request starts, no redirects and no automatic HTTP retries. Raw response text and its UTC fetch time stay in ignored `.cache/understat/matches/<id>.json`. A lock prevents simultaneous archive writers against the same cache. Successful responses and failed attempts are cached; a normal rerun makes no requests once every match has an attempt. Use `--retry-failed` explicitly to retry transport/HTTP/JSON failures; invalid sheets remain excluded without another download.

From the repository root, with the existing Python environment:

```bash
PYTHONDONTWRITEBYTECODE=1 python scripts/fetch_understat_rosters.py \
  --league-cache /Users/hedibelkahia/codes/football/.cache/understat
# Derive again from the same cached responses, without network access:
PYTHONDONTWRITEBYTECODE=1 python scripts/fetch_understat_rosters.py \
  --league-cache /Users/hedibelkahia/codes/football/.cache/understat --offline
```

All 60 league listings must exist before fetching starts; none are downloaded or refreshed. `league_sources.json` records their source URLs, cache fetch times (Unix seconds) and SHA-256 hashes of the cached content. A run resumes at missing match IDs and checkpoints derived files after each season. Raw caches survive interruption; an interrupted request without a saved response is attempted again. `--max-fetch N` limits new requests for a small verification run. Derived CSVs use UTF-8, deterministic gzip headers and atomic replacement; identical inputs leave bytes and modification times unchanged. A custom `--output` directory receives the same README template.

## Files and fields

Each `<league>/<season>.csv.gz` contains only appearances from complete validated matches. Each row has `match_id`, `date` (provider kickoff, interpreted as UTC as in the existing xG loader), `side` (`h`/`a`), `team`, `player_id` (Understat only), `name`, `position`, `minutes`, `appearance` (`starter`/`substitute`), `roster_id`, `roster_in`, `roster_out`, `goals`, `shots`, `xg`, `xa`, `key_passes`, `yellow_cards`, `red_cards` and `fetched_at` (UTC). `position == Sub` identifies substitute appearances. Roster links are match appearance IDs, **not player IDs**; zero is the provider's no-link sentinel. `roster_id` makes the links resolvable within a match and side.

`team_games.csv.gz` has two rows per complete match: `league`, `season`, `match_id`, `date`, `side`, `team`, `opponent`, `xg_for`, `xg_against`, `league_xg_for`, `league_xg_against`. Match xG is the penalty-inclusive sum of that side's shots in the fetched match payload, excluding `OwnGoal` shots as in the existing match-event code, independently checked against roster totals. Shot match IDs, sides, dates and team names must agree with the league listing. The separate `league_xg_*` columns preserve the cached league totals. **The first samples showed differences between older league totals and newly fetched match shots/rosters** (e.g. match 4749 home: league 1.166350, shots 1.206407, players 1.206407). These source vintages are not silently substituted for one another; training targets use the match-payload totals consistent with these player rows. `exclusions.csv` records league, season, match ID/date, the first failed validation or fetch reason, and fetch time. No rows from either side of an excluded match enter either training file. Pending matches have no cached attempt yet and are counted separately below.

Each match requires eleven starters per side, unique positive player IDs across both sides, minutes in 0–130, matching side/team/roster IDs, resolvable roster links and finite nonnegative statistics. Each side's summed player xG must differ from the match shot xG by at most **0.001 absolute xG**, allowing provider rounding. No missing values are filled with zero. Understat records appearances, not unused bench players or reasons for absence. Its minutes exclude stoppage time and must remain separate from UEFA minutes.

These are retrospective observations fetched on the dates below, not archived pre-kickoff lineups or contemporary availability records. No EA identity joins or ratings are inferred, and no site, model defaults or forecast probabilities consume this archive. Historical training must respect result availability and rating vintage dates.

## Coverage and fetch dates

The table is regenerated from cached attempts. A complete sheet means both sides passed every check; excluded games have a reason in `exclusions.csv`. Pending counts remain visible while the background fetch is running.

<!-- coverage -->

| League | Season | Games | Complete sheets | Excluded | Pending | First fetch (UTC) | Last fetch (UTC) |
| :--- | :--- | ---: | ---: | ---: | ---: | :--- | :--- |
| EPL | 2014/15 | 380 | 23 | 0 | 357 | 2026-10-16T00:33:59.837967+00:00 | 2026-10-16T00:35:09.119324+00:00 |
| EPL | 2015/16 | 380 | 0 | 0 | 380 | — | — |
| EPL | 2016/17 | 380 | 1 | 0 | 379 | 2026-10-16T00:32:44.746050+00:00 | 2026-10-16T00:32:44.746050+00:00 |
| EPL | 2017/18 | 380 | 0 | 0 | 380 | — | — |
| EPL | 2018/19 | 380 | 0 | 0 | 380 | — | — |
| EPL | 2019/20 | 380 | 0 | 0 | 380 | — | — |
| EPL | 2020/21 | 380 | 0 | 0 | 380 | — | — |
| EPL | 2021/22 | 380 | 0 | 0 | 380 | — | — |
| EPL | 2022/23 | 380 | 0 | 0 | 380 | — | — |
| EPL | 2023/24 | 380 | 0 | 0 | 380 | — | — |
| EPL | 2024/25 | 380 | 0 | 0 | 380 | — | — |
| EPL | 2025/26 | 380 | 0 | 0 | 380 | — | — |
| La_liga | 2014/15 | 380 | 0 | 0 | 380 | — | — |
| La_liga | 2015/16 | 380 | 0 | 0 | 380 | — | — |
| La_liga | 2016/17 | 380 | 0 | 0 | 380 | — | — |
| La_liga | 2017/18 | 380 | 0 | 0 | 380 | — | — |
| La_liga | 2018/19 | 380 | 0 | 0 | 380 | — | — |
| La_liga | 2019/20 | 380 | 0 | 0 | 380 | — | — |
| La_liga | 2020/21 | 380 | 0 | 0 | 380 | — | — |
| La_liga | 2021/22 | 380 | 0 | 0 | 380 | — | — |
| La_liga | 2022/23 | 380 | 0 | 0 | 380 | — | — |
| La_liga | 2023/24 | 380 | 0 | 0 | 380 | — | — |
| La_liga | 2024/25 | 380 | 0 | 0 | 380 | — | — |
| La_liga | 2025/26 | 380 | 0 | 0 | 380 | — | — |
| Bundesliga | 2014/15 | 306 | 0 | 0 | 306 | — | — |
| Bundesliga | 2015/16 | 306 | 0 | 0 | 306 | — | — |
| Bundesliga | 2016/17 | 306 | 0 | 0 | 306 | — | — |
| Bundesliga | 2017/18 | 306 | 0 | 0 | 306 | — | — |
| Bundesliga | 2018/19 | 306 | 0 | 0 | 306 | — | — |
| Bundesliga | 2019/20 | 306 | 0 | 0 | 306 | — | — |
| Bundesliga | 2020/21 | 306 | 0 | 0 | 306 | — | — |
| Bundesliga | 2021/22 | 306 | 0 | 0 | 306 | — | — |
| Bundesliga | 2022/23 | 306 | 0 | 0 | 306 | — | — |
| Bundesliga | 2023/24 | 306 | 0 | 0 | 306 | — | — |
| Bundesliga | 2024/25 | 306 | 0 | 0 | 306 | — | — |
| Bundesliga | 2025/26 | 306 | 0 | 0 | 306 | — | — |
| Serie_A | 2014/15 | 380 | 0 | 0 | 380 | — | — |
| Serie_A | 2015/16 | 380 | 0 | 0 | 380 | — | — |
| Serie_A | 2016/17 | 380 | 0 | 0 | 380 | — | — |
| Serie_A | 2017/18 | 380 | 0 | 0 | 380 | — | — |
| Serie_A | 2018/19 | 380 | 0 | 0 | 380 | — | — |
| Serie_A | 2019/20 | 380 | 0 | 0 | 380 | — | — |
| Serie_A | 2020/21 | 380 | 0 | 0 | 380 | — | — |
| Serie_A | 2021/22 | 380 | 0 | 0 | 380 | — | — |
| Serie_A | 2022/23 | 380 | 0 | 0 | 380 | — | — |
| Serie_A | 2023/24 | 380 | 0 | 0 | 380 | — | — |
| Serie_A | 2024/25 | 380 | 0 | 0 | 380 | — | — |
| Serie_A | 2025/26 | 380 | 0 | 0 | 380 | — | — |
| Ligue_1 | 2014/15 | 380 | 0 | 0 | 380 | — | — |
| Ligue_1 | 2015/16 | 380 | 0 | 0 | 380 | — | — |
| Ligue_1 | 2016/17 | 380 | 0 | 0 | 380 | — | — |
| Ligue_1 | 2017/18 | 380 | 0 | 0 | 380 | — | — |
| Ligue_1 | 2018/19 | 380 | 0 | 0 | 380 | — | — |
| Ligue_1 | 2019/20 | 279 | 0 | 0 | 279 | — | — |
| Ligue_1 | 2020/21 | 380 | 0 | 0 | 380 | — | — |
| Ligue_1 | 2021/22 | 380 | 0 | 0 | 380 | — | — |
| Ligue_1 | 2022/23 | 380 | 0 | 0 | 380 | — | — |
| Ligue_1 | 2023/24 | 306 | 0 | 0 | 306 | — | — |
| Ligue_1 | 2024/25 | 306 | 0 | 0 | 306 | — | — |
| Ligue_1 | 2025/26 | 306 | 0 | 0 | 306 | — | — |
