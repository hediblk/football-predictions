# Odds archive

Daily bookmaker 1X2 observations, appended by `scripts/archive_odds.py` during the site refresh (see the [README](../../README.md)). One archive per competition and season: `<season>/<code>.csv`, with `<season>` the July-based start year and `<code>` one of `PL`, `PD`, `BL1`, `SA`, `FL1`, `CL`, `EL` (Europa League, from 13 October 2026) and `ECL` (Conference League, same date). The five domestic leagues also have a sibling `<code>_prices.csv` with raw decimal prices; existing readers continue to use `<code>.csv`. Rows are only ever appended.

Domestic requests include both `h2h` and `totals` for the 2.5 line; the other competitions request `h2h`. Actual credit use can vary with the API response, so the script prints `x-requests-last`, `x-requests-used`, and `x-requests-remaining` when the response includes them. These are displayed as quota metadata only and are never written to the odds CSVs. A cache hit has no fresh response headers and therefore reports no quota values.

At one region with both domestic markets returned, the expected total is 13 credits a day (five domestic requests at two credits and three European requests at one), or 390 per 30 days. A live Premier League combined-market check returned `x-requests-last: 2`, with 21 fixtures and 21 valid 2.5 totals pairs; it wrote no archive observations. The [API documentation](https://the-odds-api.com/liveapi/guides/v4/#usage-quota-costs-1) defines usage per returned market and region; response headers remain the actual accounting.

Each row is one fixture as quoted at one fetch, from [The Odds API](https://the-odds-api.com/) region `eu`:

| Column | Meaning |
| :--- | :--- |
| `fetched_at`, `observed_at` | When the prices were fetched (UTC); `observed_at` repeats it so a file works as `--odds-snapshot` |
| `competition`, `match_id` | Competition code and The Odds API event id |
| `commence_time` | Kickoff (UTC) |
| `home_team`, `away_team` | The Odds API names; match them to football-data.org with `normalize_team` |
| `books`, `last_update` | Bookmakers quoting the fixture, and their latest price update |
| `p_home_book`, `p_draw_book`, `p_away_book` | Mean of each bookmaker's de-margined probabilities, renormalized |
| `pinnacle_home`, `pinnacle_draw`, `pinnacle_away` | Pinnacle's de-margined probabilities, when it quotes |

The sibling `<code>_prices.csv` has `fetched_at`, `competition`, `match_id`, `commence_time`, `observed_at`, `home_team`, and `away_team` keys, plus these decimal-price fields:

| Columns | Meaning |
| :--- | :--- |
| `average_home`, `average_draw`, `average_away` | Arithmetic mean of quoted raw 1X2 prices across bookmakers |
| `best_home`, `best_draw`, `best_away` | Highest raw 1X2 price quoted across bookmakers |
| `pinnacle_home`, `pinnacle_draw`, `pinnacle_away` | Pinnacle's raw decimal 1X2 prices, when available |
| `average_over_2_5`, `average_under_2_5` | Arithmetic mean of raw prices at the 2.5 totals line |
| `best_over_2_5`, `best_under_2_5` | Highest raw price at the 2.5 totals line |
| `pinnacle_over_2_5`, `pinnacle_under_2_5` | Pinnacle's raw prices at the 2.5 totals line, when available |

Missing quotes are blank. The standard totals endpoint returns the offered main line; only complete Over/Under pairs at exactly 2.5 are included, so fixtures offered at other lines can have no totals prices. The totals are archived for the five domestic leagues only. `observed_at` is the fetch time; `last_update` is not currently included in this sibling file. The raw-price file is not an odds snapshot: forecasts continue to read only the de-margined probabilities in `<code>.csv`. Average and best prices are aggregate benchmarks; Pinnacle prices are named-book offers.

Margins are removed proportionally. Forecasts only use a quote observed before both the forecast origin and kickoff (`match_odds`).
