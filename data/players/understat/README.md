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
| EPL | 2014/15 | 380 | 380 | 0 | 0 | 2026-10-16T00:33:59.837967+00:00 | 2026-10-16T06:50:53.545084+00:00 |
| EPL | 2015/16 | 380 | 380 | 0 | 0 | 2026-10-16T00:43:08.012612+00:00 | 2026-10-16T00:49:28.398245+00:00 |
| EPL | 2016/17 | 380 | 380 | 0 | 0 | 2026-10-16T00:32:44.746050+00:00 | 2026-10-16T00:55:49.041564+00:00 |
| EPL | 2017/18 | 380 | 380 | 0 | 0 | 2026-10-16T00:55:50.472681+00:00 | 2026-10-16T01:02:10.951689+00:00 |
| EPL | 2018/19 | 380 | 380 | 0 | 0 | 2026-10-16T01:02:12.837389+00:00 | 2026-10-16T01:08:33.314723+00:00 |
| EPL | 2019/20 | 380 | 380 | 0 | 0 | 2026-10-16T01:08:35.712788+00:00 | 2026-10-16T06:51:17.092875+00:00 |
| EPL | 2020/21 | 380 | 379 | 1 | 0 | 2026-10-16T01:15:27.726015+00:00 | 2026-10-16T01:21:48.172486+00:00 |
| EPL | 2021/22 | 380 | 380 | 0 | 0 | 2026-10-16T01:21:51.103099+00:00 | 2026-10-16T01:28:11.473775+00:00 |
| EPL | 2022/23 | 380 | 380 | 0 | 0 | 2026-10-16T01:28:14.855624+00:00 | 2026-10-16T01:34:35.245221+00:00 |
| EPL | 2023/24 | 380 | 380 | 0 | 0 | 2026-10-16T01:34:39.772740+00:00 | 2026-10-16T01:41:00.162277+00:00 |
| EPL | 2024/25 | 380 | 380 | 0 | 0 | 2026-10-16T01:41:04.142382+00:00 | 2026-10-16T01:47:25.087126+00:00 |
| EPL | 2025/26 | 380 | 380 | 0 | 0 | 2026-10-16T01:47:29.426955+00:00 | 2026-10-16T01:53:50.215292+00:00 |
| La_liga | 2014/15 | 380 | 379 | 1 | 0 | 2026-10-16T01:53:54.920905+00:00 | 2026-10-16T02:00:15.450958+00:00 |
| La_liga | 2015/16 | 380 | 380 | 0 | 0 | 2026-10-16T02:00:21.580855+00:00 | 2026-10-16T06:51:39.559632+00:00 |
| La_liga | 2016/17 | 380 | 380 | 0 | 0 | 2026-10-16T02:06:47.329394+00:00 | 2026-10-16T02:13:08.735188+00:00 |
| La_liga | 2017/18 | 380 | 380 | 0 | 0 | 2026-10-16T02:13:14.501739+00:00 | 2026-10-16T02:19:36.183863+00:00 |
| La_liga | 2018/19 | 380 | 380 | 0 | 0 | 2026-10-16T02:19:44.077597+00:00 | 2026-10-16T02:26:04.704499+00:00 |
| La_liga | 2019/20 | 380 | 380 | 0 | 0 | 2026-10-16T02:26:11.365241+00:00 | 2026-10-16T02:32:31.917757+00:00 |
| La_liga | 2020/21 | 380 | 380 | 0 | 0 | 2026-10-16T02:32:38.886635+00:00 | 2026-10-16T02:38:59.321499+00:00 |
| La_liga | 2021/22 | 380 | 380 | 0 | 0 | 2026-10-16T02:39:06.748092+00:00 | 2026-10-16T02:45:27.387322+00:00 |
| La_liga | 2022/23 | 380 | 380 | 0 | 0 | 2026-10-16T02:45:35.586488+00:00 | 2026-10-16T02:51:56.024476+00:00 |
| La_liga | 2023/24 | 380 | 379 | 1 | 0 | 2026-10-16T02:52:04.687146+00:00 | 2026-10-16T02:58:25.224900+00:00 |
| La_liga | 2024/25 | 380 | 380 | 0 | 0 | 2026-10-16T02:58:33.669859+00:00 | 2026-10-16T03:04:55.023024+00:00 |
| La_liga | 2025/26 | 380 | 379 | 1 | 0 | 2026-10-16T03:05:04.336721+00:00 | 2026-10-16T03:11:26.080931+00:00 |
| Bundesliga | 2014/15 | 306 | 305 | 1 | 0 | 2026-10-16T03:11:35.381323+00:00 | 2026-10-16T03:16:42.597618+00:00 |
| Bundesliga | 2015/16 | 306 | 306 | 0 | 0 | 2026-10-16T03:16:52.029307+00:00 | 2026-10-16T03:21:59.204911+00:00 |
| Bundesliga | 2016/17 | 306 | 306 | 0 | 0 | 2026-10-16T03:22:08.965732+00:00 | 2026-10-16T03:27:16.034935+00:00 |
| Bundesliga | 2017/18 | 306 | 306 | 0 | 0 | 2026-10-16T03:27:26.090139+00:00 | 2026-10-16T03:32:32.477621+00:00 |
| Bundesliga | 2018/19 | 306 | 306 | 0 | 0 | 2026-10-16T03:32:42.823429+00:00 | 2026-10-16T03:37:50.063842+00:00 |
| Bundesliga | 2019/20 | 306 | 306 | 0 | 0 | 2026-10-16T03:38:00.753107+00:00 | 2026-10-16T03:43:07.791536+00:00 |
| Bundesliga | 2020/21 | 306 | 306 | 0 | 0 | 2026-10-16T03:43:18.788499+00:00 | 2026-10-16T03:48:25.082300+00:00 |
| Bundesliga | 2021/22 | 306 | 306 | 0 | 0 | 2026-10-16T03:48:36.276446+00:00 | 2026-10-16T03:53:42.914396+00:00 |
| Bundesliga | 2022/23 | 306 | 306 | 0 | 0 | 2026-10-16T03:53:54.467062+00:00 | 2026-10-16T03:59:01.371245+00:00 |
| Bundesliga | 2023/24 | 306 | 306 | 0 | 0 | 2026-10-16T03:59:13.179881+00:00 | 2026-10-16T04:04:20.430459+00:00 |
| Bundesliga | 2024/25 | 306 | 305 | 1 | 0 | 2026-10-16T04:04:32.609113+00:00 | 2026-10-16T04:09:38.987075+00:00 |
| Bundesliga | 2025/26 | 306 | 306 | 0 | 0 | 2026-10-16T04:09:51.440945+00:00 | 2026-10-16T04:14:58.234780+00:00 |
| Serie_A | 2014/15 | 380 | 379 | 1 | 0 | 2026-10-16T04:15:10.937271+00:00 | 2026-10-16T04:21:32.621210+00:00 |
| Serie_A | 2015/16 | 380 | 380 | 0 | 0 | 2026-10-16T04:21:45.900204+00:00 | 2026-10-16T04:28:06.644598+00:00 |
| Serie_A | 2016/17 | 380 | 380 | 0 | 0 | 2026-10-16T04:28:20.112994+00:00 | 2026-10-16T04:34:41.957689+00:00 |
| Serie_A | 2017/18 | 380 | 380 | 0 | 0 | 2026-10-16T04:34:55.740590+00:00 | 2026-10-16T04:41:17.100312+00:00 |
| Serie_A | 2018/19 | 380 | 380 | 0 | 0 | 2026-10-16T04:41:31.698741+00:00 | 2026-10-16T04:47:52.341419+00:00 |
| Serie_A | 2019/20 | 380 | 380 | 0 | 0 | 2026-10-16T04:48:07.034463+00:00 | 2026-10-16T04:54:27.795847+00:00 |
| Serie_A | 2020/21 | 380 | 380 | 0 | 0 | 2026-10-16T04:54:42.744541+00:00 | 2026-10-16T05:01:03.228291+00:00 |
| Serie_A | 2021/22 | 380 | 380 | 0 | 0 | 2026-10-16T05:01:18.700358+00:00 | 2026-10-16T05:07:39.247536+00:00 |
| Serie_A | 2022/23 | 380 | 380 | 0 | 0 | 2026-10-16T05:07:54.935482+00:00 | 2026-10-16T05:14:15.466548+00:00 |
| Serie_A | 2023/24 | 380 | 380 | 0 | 0 | 2026-10-16T05:14:31.567581+00:00 | 2026-10-16T05:20:52.079259+00:00 |
| Serie_A | 2024/25 | 380 | 380 | 0 | 0 | 2026-10-16T05:21:08.559962+00:00 | 2026-10-16T05:27:29.060215+00:00 |
| Serie_A | 2025/26 | 380 | 380 | 0 | 0 | 2026-10-16T05:27:46.268764+00:00 | 2026-10-16T05:34:06.909047+00:00 |
| Ligue_1 | 2014/15 | 380 | 377 | 3 | 0 | 2026-10-16T05:34:24.788377+00:00 | 2026-10-16T05:40:45.254987+00:00 |
| Ligue_1 | 2015/16 | 380 | 378 | 2 | 0 | 2026-10-16T05:41:03.559242+00:00 | 2026-10-16T05:47:24.062121+00:00 |
| Ligue_1 | 2016/17 | 380 | 379 | 1 | 0 | 2026-10-16T05:47:42.041239+00:00 | 2026-10-16T05:54:02.448933+00:00 |
| Ligue_1 | 2017/18 | 380 | 379 | 1 | 0 | 2026-10-16T05:54:21.118913+00:00 | 2026-10-16T06:00:41.510313+00:00 |
| Ligue_1 | 2018/19 | 380 | 380 | 0 | 0 | 2026-10-16T06:01:00.444078+00:00 | 2026-10-16T06:07:20.781385+00:00 |
| Ligue_1 | 2019/20 | 279 | 279 | 0 | 0 | 2026-10-16T06:07:39.965039+00:00 | 2026-10-16T06:12:18.984303+00:00 |
| Ligue_1 | 2020/21 | 380 | 380 | 0 | 0 | 2026-10-16T06:12:38.510598+00:00 | 2026-10-16T06:18:59.082602+00:00 |
| Ligue_1 | 2021/22 | 380 | 380 | 0 | 0 | 2026-10-16T06:19:18.821883+00:00 | 2026-10-16T06:25:39.465371+00:00 |
| Ligue_1 | 2022/23 | 380 | 379 | 1 | 0 | 2026-10-16T06:25:59.924561+00:00 | 2026-10-16T06:32:20.454486+00:00 |
| Ligue_1 | 2023/24 | 306 | 306 | 0 | 0 | 2026-10-16T06:32:40.829241+00:00 | 2026-10-16T06:37:47.089376+00:00 |
| Ligue_1 | 2024/25 | 306 | 306 | 0 | 0 | 2026-10-16T06:38:08.256309+00:00 | 2026-10-16T06:43:14.612489+00:00 |
| Ligue_1 | 2025/26 | 306 | 305 | 1 | 0 | 2026-10-16T06:43:36.105721+00:00 | 2026-10-16T06:48:42.324481+00:00 |
