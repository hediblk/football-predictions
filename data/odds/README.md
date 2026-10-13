# Odds archive

Daily bookmaker 1X2 prices, appended by `scripts/archive_odds.py` during the site refresh (see the [README](../../README.md)). One CSV per competition and season: `<season>/<code>.csv`, with `<season>` the July-based start year and `<code>` one of `PL`, `PD`, `BL1`, `SA`, `FL1`, `CL`. Rows are only ever appended.

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

Margins are removed proportionally. Forecasts only use a quote observed before both the forecast origin and kickoff (`match_odds`).
