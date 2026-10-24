# Research backlog, 24 October 2026

These are model ideas taken from the football-forecasting literature, written so each can be picked up later on its own. It complements the [project opportunities catalogue](project-opportunities-2026-10-19.md); items there (P1–P15, M1–M8) are not repeated. Nothing here is a commitment, and nothing here changes defaults or `calibrated_weights.json`.

**What counts as an improvement.** Published forecasts come from the **no-odds** blend: the daily refresh runs `football-predict --no-use-odds`, and the Champions League uses archived prices only inside its strength fit. An idea only helps the site if it improves that blend, or the season and tournament simulations built on it. Gains for odds-blended forecasts do not reach the site (see R1/R2).

**Shared protocol.** All of these use the saved calibration dataset (`out/global-calibration/features/dataset.csv`, hash-checked against the artifact):

- Score log loss with equal league-season weights, on identical fixtures.
- Fit on earlier seasons only. The primary design is an expanding window over 2017/18–2025/26; also report the 2024/25–2025/26 holdout.
- Cluster SEs by league-season; 0.0005 is the yardstick.
- Use fixed seeds for simulations, and the relevant standings or stage metrics for simulation changes.
- Fix the hypothesis, variants and thresholds before looking at results.
- Seasons that informed the xG weight and scale are not an independent test of the whole model; the six robustness leagues (P1, N1, B1, T1, G1, SC0) are.

## Done

### R1 and R2: free market pool and margin removal (tested, not adopted)

These were tested on 24 October 2026 in the closed [hediblk/football-predictions#70](https://github.com/hediblk/football-predictions/pull/70). That PR's branch `codex/market-blend-experiments` keeps the code (`forecast_calibration.market_blend`) and the full report (`docs/market-blend-and-margins.md`).

- **R1, free log-linear pool** (Benter's second stage; weights need not sum to one):
  - Odds-blended forecast improves by 0.0006 (SE 0.0004) on the top five, expanding window, and by 0.0019 on the outside leagues.
  - The no-odds blend does not improve: +0.00014 (SE 0.00011). It is already at its free optimum.
- **R2, margin removal:** power and Shin removal beat proportional removal in every test: −0.00034 (SE 0.0002) on the top five, −0.0017 outside. The gain mostly overlaps R1, since a fitted market coefficient learns the same longshot correction.
- **Why not adopted:** published forecasts do not blend odds.
- **Lessons to keep:**
  - **The market's departures from our model are informative.** The free pool weights our model at −0.07 to −0.21 and the market at 1.12–1.26. Everything our model knows is already priced.
  - **The model–market gap depends on the time of year.** It is 0.0088 in January–March but 0.0176 in July–September and 0.0163 in April–June, and 0.0159 against 0.0120 with a promoted club. This motivated R3.
- **If odds are ever blended:** use power removal and a free pool, refitted by `football-calibrate`.
- **For the market comparison (feature-plan Task 14):** compare with power-de-margined prices. Proportional removal understates the market by 0.0003–0.0017.

### R3: late-season stakes (tested, not adopted)

Report: [late-season stakes](late-season-stakes.md); code: `forecast_calibration.late_stakes`.

- **Gap by stakes:** after half the season, fixtures where exactly one side has nothing to play for trail the market by 0.0171, against 0.0091 when both sides play for something.
- **Stakes term:** a shift from historically simulated stakes changes held-out log loss by −0.00010 (SE 0.00031). It is −0.00026 and −0.00032 at the 1-point and 10-point thresholds, all below the yardstick.
- **Direction:** the motivated side gains about 0.1 logit, and dead rubbers draw less, consistently across folds. The market already prices this.
- **Left open:** a lineup or rotation check restricted to these late one-sided fixtures.

## Open

### R4: goal distribution beyond Poisson

- **Idea:** football scores can be less dispersed than Poisson. Dixon–Coles corrects only scores up to 1–1, through ρ (`dixon_coles.py`). A bivariate Weibull count model or Conway–Maxwell–Poisson margins change the whole score grid, mainly draws and totals.
- **Sources:**
  - Boshnakov, Kharrat and McHale, "A bivariate Weibull count model for forecasting association football scores", *International Journal of Forecasting* (2017).
  - Florez, Guindani and Vannucci, [Bayesian bivariate Conway–Maxwell–Poisson regression](https://arxiv.org/html/2409.17129v1) (2024).
- **Check first (cheap):** calibration of goal totals. This is M8 in the catalogue.
  - Bin the dataset's fixtures by predicted P(over 2.5) and P(both teams score), and compare with observed rates. Do the same for the draw probability.
  - If the bins are calibrated within noise, stop here.
  - The site already publishes `o25` and `btts` per fixture (`scripts/build_site_data.py`), so miscalibration there is visible even without a 1X2 gain.
- **Experiment, if miscalibrated:**
  - Add a dispersion parameter per venue, or a Weibull shape, to the score grid. Fit it on earlier seasons with today's strengths held fixed, so only the distribution changes.
  - Score log loss on 1X2 and on exact scores.
  - Then replay title and top-four Brier scores, since points totals depend on draws.
- **Effort:** small for the check; medium for the model, which needs a new score grid inside `score_matrix_from_rates` and its gradients.
- **Pitfalls:**
  - Keep the reduction from score matrix to outcomes unchanged; the numerical protection compares it.
  - Ley et al. (2019) found bivariate Poisson covariance close to zero, so don't expect gains from correlation alone.

### R5: strength uncertainty in the Champions League

- **Idea:** tournament probabilities treat fitted strengths as known. For clubs from leagues with few European games, the estimates are uncertain, and averaging over that uncertainty spreads stage probabilities.
- **Source:** Corona, Forrest, Tena Horrillo and Wiper, ["Bayesian forecasting of UEFA Champions League under alternative seeding regimes"](https://livrepository.liverpool.ac.uk/3024218/), *International Journal of Forecasting* (2019).
- **Past evidence:** adding strength uncertainty was tested for domestic titles and rejected (PLAN.md, Plan C). Favourites already won as often as forecast, and noise made title forecasts worse. The roadmap leaves it open for the Champions League offsets only.
- **Experiment:**
  - Bootstrap the joint fit (`champions_league.strengths.fit_strengths`): resample matches within league-season blocks, refit, and simulate each draw with a fixed seed.
  - Alternatively, sample league offsets from the curvature of the fit at its optimum.
  - Compare stage Brier scores and match log loss in the existing replay (`football-ucl --evaluate`, 2024/25–2025/26), split by league coverage.
- **When:** after the 10 December market-weight recheck, which may move the league offsets this would sample around.
- **Effort:** medium. Bootstrap refits multiply runtime, so run them in the background with reduced simulations per draw.
- **Pitfalls:** only two replay seasons, so tournament metrics are noisy. Report the per-origin metrics and avoid tuning to the 2024/25 and 2025/26 winners.

### R6: dynamic team strengths as a benchmark

- **Idea:** let attack and defence follow a random walk or a score-driven update, instead of time decay plus Elo. This is the best-supported modelling change in the literature. It is parked in the roadmap as a bigger change.
- **Sources:**
  - Koopman and Lit, ["A dynamic bivariate Poisson model for analysing and forecasting match results in the English Premier League"](https://papers.tinbergen.nl/17062.pdf), *JRSS A* (2015), and their later score-driven version.
  - [Bayesian weighted dynamic models](https://arxiv.org/html/2508.05891v1) (2025).
- **Experiment:**
  - Implement a score-driven (GAS) Poisson update with two or three parameters (learning rates for attack and defence, plus home advantage) as a standalone benchmark. Fit on earlier seasons and score on the dataset's origins.
  - Compare with today's no-odds blend.
  - Then test it as a third blend component, next to Dixon–Coles and Elo.
- **Effort:** large for a replacement; medium for a benchmark component.
- **Pitfalls:** replacing time decay changes the season-start priors (promoted clubs) at the same time. Report early-season and late-season results separately, in line with the R1 gap breakdown.

### R7: promoted-team and preseason priors

- **Idea:** the R1 gap breakdown shows the model trails the market most in July–September (0.0176) and with promoted clubs (0.0159 against 0.0120). That is already the parked "promoted teams and preseason priors" item (second divisions E1, SP2, D2, I2, F2 with a division offset). The new evidence makes it the clearest early-season target.
- **Experiment:**
  - Add the second divisions' results to the fit history with a shrunk division offset, as the Champions League package does for leagues.
  - Score July–October fixtures, and promoted-club fixtures separately.
  - Market values, as in the catalogue's Transfermarkt row, are an optional second prior.
- **Effort:** medium. The second-division results are in the same football-data.co.uk files.
- **Pitfalls:**
  - Promotion is known only at season end.
  - Use only results available at each origin.
  - Shrink the division offset toward a typical first-to-second-division gap, not toward zero. Plan D made the same choice for league offsets.

### R8: Who disagrees with the market (product)

- **Idea:** a weekly board of fixtures where Floodlight differs most from the bookmakers, with a running record of how those disagreements score. It is Benter's split test made visible. R1 predicts the market will usually be closer; showing that honestly is part of the forecasting record.
- **Needs:** archived quotes for published fixtures (the odds archive, `data/odds/`), and power-de-margined prices.
- **Effort:** small to medium. Exporter plus site work, with no model change.

### Data follow-ups

- **Record the bookmaker margin in the odds archive.** Rows store only de-margined probabilities. Adding each fixture's mean overround to new rows would let power removal be applied exactly to archived quotes, including the Champions League quotes in Plan E. Removing an assumed typical margin agrees with the exact result within 0.000005 log loss when the assumed margin is right, and costs about 0.0001 when it is two points off. Old rows stay as they are.
- **Sharper prices:** already partly in place. `scripts/archive_odds.py` queries The Odds API's `eu` region and stores Pinnacle's probabilities beside the consensus. On historical data, most of Pinnacle's edge over average prices disappears after power removal.

### Not worth doing

- **Manager-change effects:** well-designed studies find the post-sacking bounce is mostly regression to the mean ([van Ours and van Tuijl 2016](https://link.springer.com/article/10.1007/s10645-016-9277-0); [Erasmus summary](https://www.eur.nl/en/ese/news/irrational-managerial-changes-remain-norm-europes-top-football-leagues)). A label on club pages is fine; a probability adjustment is not.
- **Ranked probability score as the main metric:** [Wheatcroft (2021)](https://arxiv.org/pdf/1908.08980) shows log loss is the better scoring rule for football. Keep RPS secondary, as now.
- **Bivariate Poisson instead of Dixon–Coles:** the fitted covariance is near zero in comparative studies ([Ley et al. 2019](https://arxiv.org/pdf/1705.09575)).
