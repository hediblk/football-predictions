# Pipeline details

The CLI and both La Liga notebooks use `standing_prediction.predict_positions.run_prediction`. It returns a `Forecast` containing `probabilities`, `summary`, `standings`, and `metadata`, and saves the forecast.

## Data and forecast origin

Current standings and the full season schedule come from [football-data.org](https://www.football-data.org/). The pipeline checks team coverage, finished-match counts, and the remaining round-robin schedule before simulation. All non-finished fixtures are taken from the season schedule, including postponed games. Fixtures without a status fail validation. In-progress games trigger a warning and are simulated from kickoff rather than using their live score.

If a season is complete, its official standings are exported directly. The default season starts in the current year from July onward, otherwise the previous year. `--season 2026` means 2026/27.

Two prior seasons are loaded by default, primarily from [football-data.co.uk](https://www.football-data.co.uk/), with football-data.org as a fallback. `--prior-seasons` controls that history. Recent results receive more weight in Dixon–Coles; Elo ratings regress toward the league average between seasons. A team with no observed results starts with neutral attack/defense and Elo strength. Forecasting before any current-season games still requires usable historical results.

API responses and historical CSVs are cached locally. `--no-cache` bypasses the cache. Saved forecast snapshots record the input data used for each run.

## Match probabilities

1. **Dixon–Coles:** fit team attack/defense, home advantage, and low-score dependence using exponential time decay and regularization. Default `xi=0.003`, `lambda_reg=0.1`, and a score grid from 0 to 10 goals.
2. **Elo:** update ratings chronologically, account for home advantage, and estimate draw behavior from observed results.
3. **Optional odds:** remove bookmaker margin and aggregate available books from The Odds API.
4. **Blend:** combine available components in log probability space. Default weights are `main=0.35,odds=0.55,elo=0.10`; weights are redistributed across available components.

Missing odds do not prevent a forecast. Coverage is logged and saved so that a forecast using market information can be distinguished from one using only team models. Match outcomes are drawn from the blend; scorelines within each outcome use the Dixon–Coles distribution.

`--calibrate` fits a multinomial logistic calibrator using earlier seasons at several historical forecast origins. Its default training seasons are the previous three, with cutoff rounds 5, 10, 20, and 30. Forecast calibration currently uses DC/Elo features rather than undated historical odds. Compare held-out results before assuming calibration improves the forecast.

## Timestamped odds

An odds row must have been observed at or before the forecast origin and before kickoff. The fixture must match normalized home/away names and kickoff date. Undated football-data.co.uk odds are excluded from dated prediction and backtesting because their historical availability cannot be established.

Use `--odds-snapshot odds.csv` to load archived observations. Required columns are:

| Columns | Meaning |
| --- | --- |
| `observed_at` | UTC timestamp when these odds were available |
| `commence_time` or `date` | Fixture kickoff timestamp/date |
| `home_norm`, `away_norm` | Normalized team names; alternatively supply `home_team`, `away_team` for normalization |
| `p_home_book`, `p_draw_book`, `p_away_book` | Finite, nonnegative probabilities with a positive total; normalized on loading |

For example:

```csv
observed_at,commence_time,home_team,away_team,p_home_book,p_draw_book,p_away_book
2026-09-01T10:00:00Z,2026-09-02T19:00:00Z,Real Madrid CF,FC Barcelona,0.45,0.25,0.30
```

Keep multiple dated observations if collecting a historical archive. For each fixture, the latest eligible observation is selected. A live odds response or snapshot from today cannot be used to reconstruct what was known months earlier.

## Season simulation and ranking

The default forecast draws 10,000 seasons with seed 7. Sampling is vectorized across simulations. Every simulated score updates points, goals for/against, and head-to-head records, combined with matches already played.

The ranking implementation uses these sporting criteria after total points:

| Competition | Modeled tie-break order |
| --- | --- |
| La Liga (`PD`) | Two teams: head-to-head goal difference, overall goal difference, goals scored. More teams: mini-table points, mini-table goal difference, overall goal difference, goals scored; rules are reapplied to any remaining tied subset. |
| Premier League (`PL`) | Overall goal difference, goals scored, head-to-head points, head-to-head away goals. |
| Bundesliga (`BL1`) | Overall goal difference, goals scored, head-to-head aggregate goal difference, head-to-head away goals, total away goals. |
| Serie A (`SA`) | Mini-table points, mini-table goal difference, overall goal difference, goals scored. |
| Ligue 1 (`FL1`) | Overall goal difference, head-to-head points, head-to-head goal difference, goals scored, total wins, away wins. |

These are practical final-table rules, not complete competition administration. Fair-play criteria and deciding playoff matches are not simulated. In particular, Serie A title/relegation playoff exceptions are approximated by the listed sporting classification. Remaining exact ties use seeded random ordering in simulation; the ranking helper preserves input order when no random tie-break is supplied. Ligue 1 uses its rules introduced in 2025/26, including wins and away wins.

Primary references: [RFEF competition rules](https://rfef.es/sites/default/files/2025-06/1._CNL_Primera_y_Segunda_Division.pdf), [Premier League explanation](https://www.premierleague.com/en/premier-league-explained), [DFL rules, §2](https://media.dfl.de/sites/2/2020/08/Spielordnung-SpOL-2020-08-05-Stand.pdf), [FIGC NOIF](https://www.figc.it/media/276245/tit3_noif_art_da47a70_-aggiornato-al-08-07-2025.pdf), and [Ligue 1 rule changes](https://ligue1.com/en/articles/l1_article_2830-).

The old `simulate_season` probability-only helper remains for compatibility. It assumes 1–0, 0–0, or 0–1 scorelines and uses the Premier League ranking order. Supported notebooks use the full scoreline pipeline instead.

## Outputs and uncertainty

Latest files live under `out/` by default. For La Liga:

- `pd_position_probs.csv` and `pd_position_probs.html`: position percentages and a readable report.
- `pd_summary.csv`: expected position/points, `points_p10`, `points_p90`, and title/top-four/bottom-three event probabilities.
- `pd_metadata.json`: forecast generation time, last finished-match date, fixture counts, odds coverage, history, model settings, simulation seed, and limitations.
- `pd_standings_snapshot.csv`, `pd_matches_snapshot.csv`, and available timestamped `pd_odds_snapshot.csv`.

Every run is also saved to `out/snapshots/pd/<season>/<timestamp>/`, preserving earlier forecasts while the latest files remain convenient to open.

`expected_points` is the simulation mean. `points_p10` and `points_p90` bound the central 80% of simulated final points, conditional on fitted team strengths. They exclude parameter uncertainty and future changes in squads, injuries, and form.

Event Monte Carlo standard error is `100 × sqrt(p × (1 − p) / n_sim)`, in percentage points. At 10,000 simulations the largest standard error is 0.5 percentage points. It measures finite simulation noise, not forecast accuracy. Top-four/bottom-three probabilities describe positions, not league-specific qualification or relegation rules.

## Historical evaluation

```bash
football-backtest --competition PD --seasons 2022 2023 2024 --cutoffs 5 10 20 30
```

Seasons are processed chronologically. A cutoff counts `round × teams/2` completed games and advances to the end of that UTC day, including games played that day. This approximates rounds while respecting postponed games and the information available at the forecast origin.

Each origin fits base models using earlier results and prior seasons, forecasts the remaining matches, and simulates the final table. Calibrators use only earlier evaluated seasons; no calibrated score is reported for the first season. Multiple origins from one training season have overlapping forecast horizons, so their rows are not independent samples.

Default backtest size is 2,000 simulations per origin. Outputs under `out/backtests/` are `metrics.csv`, `match_forecasts.csv`, `position_forecasts.csv`, and `metadata.json`:

- Match log loss and multiclass Brier scores for DC, Elo, blend, and available calibration; bookmaker comparisons use the same odds-covered subset.
- Final-position ranked probability score (RPS), position log loss, expected position/points mean absolute errors, and title/top-four/bottom-three Brier scores.
- Position log loss clips finite-simulation zero probabilities at `1e-12`; prefer RPS and event Brier scores when interpreting sparse tails.

Historical standings and position targets are reconstructed solely from scores and the modeled sporting rules. They exclude disciplinary points deductions, appeals, and deciding playoff results; this matters particularly in the Premier League and Serie A. Backtest position scores therefore describe those modeled targets rather than guaranteeing agreement with official tables. Completed-season production exports use official positions directly.
