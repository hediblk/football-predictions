# Champions League forecasts

The separate UCL package forecasts all 36 league-phase positions and the knockout path through the final. It depends on `standing_prediction` and reads its fixed calibrated weights. Domestic league forecasts retain their existing behavior.

![Champions League standings forecast](../../docs/champions-league-forecast.png)

![Projected Champions League bracket](../../docs/champions-league-bracket.png)

[Download bracket (PDF)](../../docs/champions-league-bracket.pdf)

*October 10, 2026, 21:30 Toronto / October 11, 01:30 UTC; 10,000 simulations. Bayern München leads title probabilities at 18.99%. The displayed draw is illustrative. [Stage probabilities](../../docs/champions-league-summary.csv), [coverage](../../docs/champions-league-coverage.csv), [provenance](../../docs/champions-league-metadata.json).*

From the repository root, with `FOOTBALL_DATA_API_KEY` in `.env`:

```bash
pip install -e . -e packages/champions-league
football-ucl --season 2026 --n-sim 10000
```

Open `out/cl_forecast.html` for the heatmap, projected bracket, qualification probabilities, and per-club data coverage. CSV/JSON/PNG files, a bracket PDF and dated input snapshots are exported alongside it. `--as-of 2026-10-11T00:00:00Z` fixes the forecast origin; `--odds-snapshot path.csv` optionally supplies dated quotes for specific scheduled fixtures. The default uses no odds.

Odds CSVs use `date` (or `commence_time`), `observed_at`, `home_team`, `away_team`, `p_home`, `p_draw`, and `p_away`. Quotes must precede kickoff, match the fixture date, be available at the origin, and be at most seven days old.

```python
from dotenv import load_dotenv
from champions_league import run_forecast

load_dotenv()
forecast = run_forecast(season=2026, n_sim=10000)
forecast.probabilities
forecast.summary
forecast.bracket
```

Full domestic results, available European history, and top-five Understat xG feed one time-decayed Dixon–Coles fit. Centered club attack/defense deviations describe domestic strength; country offsets put international opponents on a common scale. Offsets shrink toward a fitted typical league level, not toward the reference league, so countries with little European evidence are not rated like the Premier League (Plan D in [PLAN.md](../../PLAN.md)). Archived Champions League prices from [data/odds](../../data/odds/README.md) enter the same fit, each weighted like ten results; they see the offsets plus a ridge-shrunk current shift per league, so the market sets each league's present level without rewriting past results (Plan E). `--odds-archive` points elsewhere and `--no-market` fits results only. Only quotes observed before both the origin and kickoff count, so the replay below is unaffected. European games have separate scoring/home baselines. Elo processes the same connected dated history. Missing xG leaves goal strengths intact; missing domestic histories and weak European links are flagged. Sparse-country title probabilities also receive a league-offset prior sensitivity check.

The schedule validator requires 144 fixtures, eight distinct opponents and four home/four away matches per club. Simulated ranking includes opponents' collective final totals. Knockout draws respect UEFA bracket slots, fix observed results, and preserve inherited home priority from 2025/26 onward. Official pairings are conditioned on when available; future pairings in the displayed bracket are illustrative. The overall title favorite averages all simulated draws and results, and can differ from the winner of one projected bracket.

Run the retrospective checks with:

```bash
football-ucl --evaluate --n-sim 2000
```

This replays 2024/25 and 2025/26 after matchdays 2, 4, 6 and 8 and before each knockout round. It exports position RPS, stage Brier scores, international match log loss against a model without league offsets, a goals-only fit, and joint Elo, including splits by xG coverage. These seasons overlap the domestic data used for global weight calibration; this is a retrospective transfer check, not an independent calibration holdout.

The [committed replay](../../docs/champions-league-evaluation.json), rerun with calibration `global-4c0170be18f1` and the Plan D league offsets, completed 18 origins and scored 306 unique subsequent matches: log loss 0.90862 for the joint model, 0.92999 without country offsets, 0.91566 for goals only and 0.98999 for Elo (rerun after Dutch and Portuguese results stopped being counted twice; previously 0.90876). The joint model scored 0.94975 under the original calibration and 0.93951 after the xG scale ([Plan C](../../PLAN.md)); shrinking offsets toward a typical league level and adding club European effects brought it to 0.90876 ([Plan D](../../PLAN.md)). [Per-origin scores](../../docs/champions-league-evaluation-snapshots.json) retain horizon and xG coverage splits.

Probabilities condition on fitted strengths. Source freshness, missing history, uneven xG coverage and two seasons of tournament evidence limit their precision. Future discipline is unmodeled, so a remaining sporting tie uses seeded randomness before the coefficient criterion; complete league phases use official ranks. Extra time uses one third of the second-leg goal rates, shootouts are 50/50, and flagged relocated venues are treated as neutral. Historical result publication and draw availability use conservative date approximations. Raw source responses are cached locally; each forecast saves normalized inputs and source versions.

The current official coefficient feed returns HTTP 403; that failure is recorded in metadata. Czech 2025/26 history is absent from the pinned source, several secondary current sources stop in September, and an Azerbaijani 2025/26 fixture score disagrees with the official table. These limitations are retained in the coverage/provenance exports. Current top-five, Portuguese and Dutch results also use the football-data.org API to refresh stale CSVs. An API club the CSV spells differently takes the CSV name of the club with the same fixtures (logged, so the alias can be added to `identities.py`); if a club would still have two results in a day, the league keeps its CSV results and records the error.

Rules: [league ranking](https://documents.uefa.com/r/Regulations-of-the-UEFA-Champions-League-2026/27/Article-18-Equality-of-points-league-phase-Online), [fixed bracket and home priority](https://documents.uefa.com/r/Regulations-of-the-UEFA-Champions-League-2026/27/Article-19-Draw-system-knockout-phase-Online), [2025/26 introduction of inherited priority](https://www.uefa.com/uefachampionsleague/news/0296-1d21e9bdf7e4-808a7511165c-1000--2025-26-champions-league-format-dates-draws-final/).
