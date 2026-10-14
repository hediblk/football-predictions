# European results archive

Finished Europa League (`EL`) and Conference League (`ECL`) matches from ESPN, appended by `scripts/archive_results.py` during the daily site refresh. No API key or paid scores endpoint is needed. One CSV per competition and season: `<season>/<code>.csv`, where `<season>` is the July-based start year determined from the UTC kickoff (`2025` means 2025/26).

Each row is one finished match from the [ESPN Europa League scoreboard](https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.europa/scoreboard?dates=20251002) or [Conference League scoreboard](https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.europa.conf/scoreboard?dates=20251002):

| Column | Meaning |
| :--- | :--- |
| `fetched_at` | When ESPN returned the result (UTC), including for backfills |
| `competition`, `espn_id` | Competition code and ESPN event ID |
| `kickoff` | Match kickoff (UTC) |
| `stage` | ESPN's event season-type slug, such as `league-phase`, `round-of-16` or `final`; this is not a matchday number |
| `home_team`, `away_team` | Unmodified ESPN display names; compare with existing clubs using `normalize_team` |
| `home_goals`, `away_goals` | ESPN's match score, including extra time when played, excluding shootout goals |
| `status` | `full time`, `after extra time` or `penalties`, from ESPN's completed status |
| `shootout_winner` | ESPN name of the club with the higher shootout score; empty unless the status is `penalties` |

Rows are only ever appended. Existing ESPN IDs are skipped across all archived seasons and competitions; later score, name or kickoff corrections never overwrite an observation. Scheduled, in-progress, postponed, cancelled, abandoned and suspended games are excluded. Postponed/cancelled and other exceptional statuses are reported, as are malformed completed results and failed requests. Only recognized completed statuses with valid scores are archived.

The default run fetches seven UTC calendar dates, including today. Backfills use inclusive bounds:

```bash
PYTHONDONTWRITEBYTECODE=1 python scripts/archive_results.py
PYTHONDONTWRITEBYTECODE=1 python scripts/archive_results.py --from 2025-07-01 --to 2026-10-14
```

Each request uses exactly one `dates=YYYYMMDD` value; ESPN rejects date ranges. All requests, including retries and requests for the other competition, start at least one second apart. Requests have a 30-second timeout and up to three attempts. Fetch or archive failures are reported and exit successfully; the workflow also marks the step non-blocking. Rerun a date range to recover missed dates or results posted outside the seven-day window.

The initial backfill scans 2025/26 and 2026/27 through 14 October 2026. [Coverage and club-name matching](../../docs/el-ecl-results-coverage.md) record counts and gaps. These files are evidence for the 10 December Champions League recheck; forecasts do not read them yet. `fetched_at` is the first archived observation, not a historical result publication time. A later historical replay must record any availability approximation and distinguish 90-minute results from scores including extra time; do not treat this backfill as evidence available at an earlier forecast origin.
