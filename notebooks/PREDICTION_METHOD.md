# La Liga notebook guide

Both root-level La Liga notebooks use the same pipeline as `football-predict`:

- `laliga_prediction.ipynb`: compact forecast walkthrough, replacing the original simple Poisson notebook.
- `laliga_prediction_upgraded.ipynb`: the same shared forecast with editable configuration.

They display a summary and a team × finishing-position probability heatmap. Forecast exports are written by the shared pipeline, so notebook and CLI behavior stay aligned.

## Setup

From the repository root, follow [the README](../README.md) to install `pip install -e '.[notebook]'`, create `.env`, and set `FOOTBALL_DATA_API_KEY`. `ODDS_API_KEY` is optional. Start `jupyter lab`, open either La Liga notebook, and run its cells in order.

The notebooks use `season=None` to infer the current European season. Set a start year such as `2026` explicitly to forecast 2026/27. Set `use_odds=False` for a forecast using only team models.

## Shared Python API

```python
from dotenv import load_dotenv
from standing_prediction.predict_positions import run_prediction

load_dotenv()
forecast = run_prediction(
    competition="PD",
    season=None,
    n_sim=10000,
    seed=7,
    use_odds=True,
    calibrate=False,
    out_dir="out",
)

forecast.summary
forecast.probabilities
forecast.metadata
```

`run_prediction` loads the data, fits Dixon–Coles/Elo using the current and up to two prior seasons, applies available timestamped odds, validates the schedule, simulates scorelines with league ranking rules, and saves the outputs. Unplayed teams without observed history start at neutral strength. Optional calibration uses earlier seasons.

The returned `probabilities` are percentages. `summary` includes expected position, expected points, 10th–90th point percentiles, event percentages, and Monte Carlo standard errors in percentage points. Point intervals are conditional on fitted strengths; they do not cover every source of model uncertainty. Bottom three means the last three positions, which is not equivalent to direct relegation in every league.

Latest La Liga results appear in `out/pd_position_probs.html`, `out/pd_position_probs.csv`, `out/pd_summary.csv`, and `out/pd_metadata.json`, with input snapshots and a timestamped archive under `out/snapshots/pd/<season>/<timestamp>/`.

See [pipeline details](../PIPELINE_DETAILS.md) for dated odds archives, historical backtesting, ranking criteria, and fair-play/playoff limitations. The legacy `standing_prediction/model.py` baseline and `simulate_season` wrapper remain for compatibility, but neither notebook duplicates that pipeline.

## External reference

`202601 - 7 - Predicting Premier League Final Positions Using Betting Odds, Probabilistic Modelling & Simulation.ipynb` is a credited external reference by Victoria Friss de Kereki. It uses separate scraping and simulation code and is not a supported notebook entry point for this package.
