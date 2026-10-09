# Football standings prediction

A Python package for forecasting final league positions from played matches, current standings, and optional bookmaker odds. The source lives in `src/standing_prediction`; the CLI and notebook use the same pipeline.

The model combines time-decayed Dixon–Coles goal probabilities with Elo, then simulates the remaining scorelines. Supported leagues are La Liga (`PD`), Premier League (`PL`), Bundesliga (`BL1`), Serie A (`SA`), and Ligue 1 (`FL1`).

## Install

Requires Python 3.11 or newer. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

Set `FOOTBALL_DATA_API_KEY` in `.env` using a key from [football-data.org](https://www.football-data.org/). Set `ODDS_API_KEY` to enable The Odds API; otherwise the forecast uses team models. Historical results come primarily from [football-data.co.uk](https://www.football-data.co.uk/).

For the pinned core dependencies used in validation, use Python 3.12 and run `pip install -r requirements-lock.txt` before `pip install -e .`.

## Python API

```python
from dotenv import load_dotenv
from standing_prediction.predict_positions import run_prediction

load_dotenv()
forecast = run_prediction(
    competition="PD",
    season=None,
    n_sim=10000,
    seed=7,
    out_dir="out",
)

forecast.probabilities  # Team × final-position percentages
forecast.summary        # Expected position/points, point intervals, event probabilities
forecast.metadata       # Data cutoff, odds coverage, settings, and provenance
```

`season=None` infers the current European season using July as the boundary; `season=2026` selects 2026/27. Two prior seasons are used by default, with time decay and Elo regression toward average strength. Teams without observed history start at neutral strength. Set `use_odds=False` to disable odds or `calibrate=True` to fit calibration using earlier seasons. Calibration is optional and does not consistently improve held-out scores.

## CLI

```bash
football-predict --competition PD
football-predict --competition PD --season 2026 --no-use-odds
football-backtest --competition PD --seasons 2022 2023 2024 --cutoffs 5 10 20 30
```

Prediction defaults to 10,000 simulations and seed 7; backtesting defaults to 2,000 simulations per snapshot. Use `--help` for options. Module entry points are also available: `python -m standing_prediction.predict_positions` and `python -m standing_prediction.backtest`.

Backtest cutoffs approximate rounds by counting completed matches chronologically and including the whole UTC day. Calibration uses expanding earlier evaluated seasons; the first evaluated season is uncalibrated. Reports in `out/backtests/` include match log loss/Brier scores, final-position ranked probability score, expected position/points errors, and event Brier scores.

## Optional notebook

```bash
pip install -e '.[notebook]'
jupyter lab notebooks/laliga_prediction.ipynb
```

Run the cells in order. The notebook calls `run_prediction` and shows the colored probability chart first, followed by run details and the summary. Continuous nonlinear colors distinguish small probabilities; labels show two decimal places.

## Outputs and odds snapshots

For La Liga, the latest forecast is `out/pd_position_probs.html`, with probabilities, summary, metadata, standings/matches snapshots, and available odds also saved as CSV/JSON. Every run is archived under `out/snapshots/pd/<season>/<timestamp>/`. Change the root with `out_dir` or `--out-dir`.

Odds must have been observed by the forecast origin and before kickoff. Historical CSV odds without observation timestamps are excluded. To use a dated archive, pass `--odds-snapshot odds.csv`; for backtesting, also pass `--use-odds`. Its columns are:

```csv
observed_at,commence_time,home_team,away_team,p_home_book,p_draw_book,p_away_book
```

Use UTC timestamps, or `date` instead of `commence_time`. Normalized `home_norm`/`away_norm` names can replace the team-name columns. Probabilities must be finite, nonnegative, and have a positive total. The latest eligible observation is matched to each fixture by team names and kickoff date.

## Limits

- Point percentiles (`points_p10`, `points_p90`) reflect match uncertainty conditional on fitted team strengths. They exclude strength-estimation error and future squad changes. Event `*_mc_se_pp` columns measure simulation sampling error in percentage points, not model error.
- Ranking models league sporting criteria, including La Liga head-to-head and tied-subset rules. Fair-play criteria and deciding playoffs are not simulated; Serie A title/relegation playoff exceptions use the modeled classification instead. Remaining exact ties use seeded randomness.
- Historical backtest tables are reconstructed from scores and modeled rules, excluding disciplinary deductions, appeals, and playoffs. They can differ from official tables, particularly in the Premier League and Serie A. Completed-season prediction exports use official positions directly.
- Top four and bottom three describe table positions, not automatic qualification or direct relegation in every league. In-progress fixtures are simulated from kickoff, with a warning.

See [PLAN.md](PLAN.md) for completed work and the next priorities.
