# La Liga Standing Prediction Method

## Overview
This project produces a table of probabilities for where each La Liga team will finish in the final league standings.
It uses finished matches to fit a simple Poisson goal model, then simulates the remaining fixtures thousands of times.

Primary artifacts:
- Notebook for visualization: `laliga_prediction.ipynb`
- Core logic: `standing_prediction/data.py`, `standing_prediction/model.py`, `standing_prediction/simulate.py`
- Output table: `standing_prediction/output/laliga_position_probs.html` (PNG optional)

## Data Sources
All live data is pulled from https://www.football-data.org/ using their REST API.
You must set `FOOTBALL_DATA_API_KEY` in your environment or `.env`.

Endpoints used:
- Standings: `/competitions/PD/standings`
- Matches: `/competitions/PD/matches`

The notebook requests:
- `status=FINISHED` for completed matches in the season
- `status=SCHEDULED,TIMED` for future fixtures

## Pipeline Summary
1. Load standings and match data from the API.
2. Fit a Poisson-based attack/defense strength model from finished matches.
3. Predict win/draw/loss probabilities for each remaining fixture.
4. Simulate the rest of the season many times to get a distribution of final positions.
5. Render a styled probability table and export to HTML (and optionally PNG).

## Detailed Logic

### 1) Data Import
Code: `standing_prediction/data.py`

- `FootballDataClient` wraps the API and injects the auth token.
- `fetch_standings` returns the current league table (team name, points, goal difference, etc.).
- `fetch_matches` returns matches for a season filtered by status.

Each match is normalized into:
`utcDate`, `matchday`, `status`, `homeTeam`, `awayTeam`, `homeGoals`, `awayGoals`.

### 2) Strength Model (Poisson)
Code: `standing_prediction/model.py`

We use a basic Poisson model:
- For each team, estimate attack and defense strength based on average goals scored and conceded.
- Compute league average goals for home and away teams.

For a match between home and away:
- Expected home goals:
  `exp_home = league_home_avg * attack[home] * defense[away]`
- Expected away goals:
  `exp_away = league_away_avg * attack[away] * defense[home]`

We then use Poisson probabilities for 0..6 goals, build a goal matrix, and derive:
- `p_home_win`
- `p_draw`
- `p_away_win`

This is intentionally simple and avoids external features like odds, Elo, or xG.

### 3) Fixture Probabilities
Code: `standing_prediction/model.py`

`predict_fixtures` applies the model to each scheduled match and returns:
`homeTeam`, `awayTeam`, `p_home_win`, `p_draw`, `p_away_win`.

### 4) Season Simulation
Code: `standing_prediction/simulate.py`

We simulate the remaining fixtures `n_sim` times:
- Start from current points and goal difference.
- For each fixture, sample the outcome using the predicted probabilities.
- Update points (3/1/0).
- After all fixtures, rank by points, then goal difference, then a tiny random tie-break.

This produces a matrix of counts: rows = teams, columns = finishing position.
We normalize the counts to percentages in the notebook.

### 5) Output
Code: `laliga_prediction.ipynb`

The notebook:
- Runs the pipeline.
- Styles the table with a green-teal heatmap and readable typography.
- Saves `laliga_position_probs.html` to `standing_prediction/output/`.
- Optionally exports a PNG using `dataframe_image`.

## Configuration
Required environment variable:
- `FOOTBALL_DATA_API_KEY`

Optional:
- `n_sim` in the notebook to control simulation size.
- `max_goals` in `StrengthModel` for Poisson truncation (default 6).

## Limitations
This is a first-pass model with known simplifications:
- No team strength priors or form weighting.
- No player injuries, transfers, or schedule congestion (baseline notebook).
- No calibration against odds (baseline notebook).

Despite this, it is a clean baseline that produces stable position distributions.

## Suggested Extensions
- Blend with bookmaker odds for future fixtures.
- Add time-decay weighting for recent matches.
- Include xG or shot-based features when available.
- Add more tie-break rules (head-to-head, goals scored).

---

# Upgraded Pipeline (Codebase)

The repository now includes a stronger, more modular pipeline that can:
- Fit a **time-decayed Dixon–Coles** (Poisson) goal model for match scorelines.
- Fit an **Elo** model as an additional strength signal.
- Optionally blend in **bookmaker odds** (The Odds API for upcoming fixtures; football-data.co.uk CSVs for historical backtests/calibration).
- Simulate the remaining season using **scorelines** (updating points, goal difference, and goals scored for tie-breaks).
- Optionally train an **ML calibrator (multinomial logistic regression)** on past seasons to map (DC + Elo + odds) -> calibrated 1X2 probabilities.

## Quick Run (CLI)
Runs the end-to-end prediction and writes `CSV + HTML` to `standing_prediction/output/`:
```bash
python3 -m standing_prediction.predict_positions --competition PD --n-sim 3000
```

### Optional: calibration (recommended if you want stronger odds blending)
```bash
python3 -m standing_prediction.predict_positions --competition PD --n-sim 3000 --calibrate
```

### Optional: odds providers
- The Odds API (upcoming fixtures): set `ODDS_API_KEY` (or `ODDS_DATA_API_KEY`) in your environment.
- football-data.co.uk (historical / backtest; no key): used automatically for calibration/backtests where available.

## Backtesting
```bash
python3 -m standing_prediction.backtest --competition PD --seasons 2022 2023 2024 --cutoff-matchday 10 --use-odds
```

## Injuries Hook
You can supply a simple team-level adjustment file:
```bash
python3 -m standing_prediction.predict_positions --injuries-csv injuries.csv
```

Expected `injuries.csv` columns:
- `team` (name; fuzzy/normalized matching is applied)
- `attack_mult` (e.g., `0.97` for a 3% reduction in scoring)
- `defense_mult` (e.g., `1.04` for a 4% increase in conceding)

## Repro Steps
1. Create `.env` with `FOOTBALL_DATA_API_KEY=...`.
2. Open `laliga_prediction.ipynb`.
3. Run all cells.
4. View `standing_prediction/output/laliga_position_probs.html`.
