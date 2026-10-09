# Pipeline Details: Upgraded La Liga Standings Predictor

This document explains how the upgraded pipeline produces season‑finish probabilities for each team. The goal is to be competitive with bookmaker‑style forecasts while remaining transparent and modular.

---

## 1) Data Sources

### Primary match + standings data (live season)
- **Source:** `https://api.football-data.org/v4`
- **Endpoints used:**
  - `/competitions/{COMP}/standings` → current table
  - `/competitions/{COMP}/matches` → finished + remaining fixtures
- **Key fields:** teams, goals, points, goal difference, match dates, matchday

### Odds data (optional, but recommended)
- **Upcoming fixtures:** The Odds API (`https://api.the-odds-api.com/v4`)
  - Market: 1X2 (`h2h`)
  - Output: decimal odds from multiple books
  - The pipeline de‑vigs and averages across books
- **Historical odds (for backtests + calibration):** `football-data.co.uk`
  - Free CSVs containing bookmaker odds (e.g., B365)

### Injuries (optional)
Simple CSV you provide:
- `team`
- `attack_mult` (e.g., `0.97` → 3% lower scoring)
- `defense_mult` (e.g., `1.04` → 4% more conceding)

---

## 2) Preprocessing and Normalization

### Team name normalization
Odds providers often use abbreviations or simplified names, so the pipeline normalizes:
- lower‑casing, stripping punctuation
- removing club suffixes (`FC`, `CF`, `CD`, `UD`, etc.)
- accent removal (e.g., `Atlético` → `Atletico`)
- known aliases (e.g., `Espanyol` → `Espanol`)

This improves odds matching across data sources.

### Season selection
The “current season” is inferred from the date:
- If month ≥ July → current year
- Else → previous year

---

## 3) Match Probability Models

The pipeline produces 1X2 probabilities using multiple signals:

### A) Dixon–Coles (time‑decayed Poisson)
Code: `standing_prediction/dixon_coles.py`

Purpose:
- Estimate attacking/defensive strengths per team.
- Model expected home/away goals.
- Apply Dixon–Coles low‑score correction (rho) to improve 0‑0, 1‑0, 0‑1 frequencies.

Key features:
- **Time decay (`xi`)**: recent matches are weighted more.
- **Regularization (`lambda_reg`)**: prevents extreme parameters.
- **Outputs:** full scoreline matrix → 1X2 probabilities.

### B) Elo rating
Code: `standing_prediction/elo.py`

Purpose:
- Provide an independent, form‑sensitive strength signal.
- Convert rating differences + home advantage into 1X2 probabilities.
- Simple draw model that shrinks as strength gap grows.

### C) Bookmaker odds (optional)
Code: `standing_prediction/odds.py`

Purpose:
- Integrate market wisdom.
- Odds are converted to probabilities and de‑vigged.

---

## 4) Probability Blending and Calibration

### Weighted blend (default)
Code: `standing_prediction/ensemble.py`

Uses a **log‑space mixture**:
```
P = softmax( w1*log(P_dc) + w2*log(P_odds) + w3*log(P_elo) )
```
This prevents any single component from dominating too strongly.

### ML Calibrator (optional)
Code: `standing_prediction/calibration.py`

Trains a **multinomial logistic regression** on past seasons:
- Features: DC probabilities, Elo probabilities, odds probabilities
- Target: actual 1X2 outcomes

Benefits:
- Learns optimal blending.
- Typically improves calibration (log loss).

---

## 5) Season Simulation

Code: `standing_prediction/simulate.py`

### Why simulate?
We want probabilities for final table positions, not just individual matches.

### How it works
1. Start from **current standings**.
2. For each remaining fixture:
   - Sample **win/draw/loss** using blended 1X2 probabilities.
   - Sample a **scoreline** (from the DC score distribution) conditional on that outcome.
3. Update **points**, **goals for**, **goals against**.
4. Sort final standings by:
   1. Points
   2. Goal difference
   3. Goals scored
   4. Random tiebreak (rare)

Repeat thousands of times → a distribution of final positions.

---

## 6) Outputs

### Core output
The primary artifact is a **team × finishing‑position probability table**, e.g.:
- `standing_prediction/output/pd_position_probs.html` (HTML)
- `standing_prediction/output/pd_position_probs.csv` (CSV)

### Notebook output
The upgraded notebook lives at:
- `output/jupyter-notebook/laliga_prediction_upgraded.ipynb`

---

## 7) Typical Workflow

**CLI run (default):**
```
python3.11 -m standing_prediction.predict_positions --competition PD --n-sim 3000
```

**With calibration (recommended):**
```
python3.11 -m standing_prediction.predict_positions --competition PD --n-sim 3000 --calibrate
```

**Backtest:**
```
python3.11 -m standing_prediction.backtest --competition PD --seasons 2022 2023 2024 --cutoff-matchday 10 --use-odds
```

---

## 8) Strengths and Limitations

### Strengths
- Blends **structural** (DC), **form** (Elo), and **market** (odds) signals.
- Uses **time‑decay** to emphasize recent matches.
- Simulates full season with realistic tie‑breaks.
- Modular: odds/injuries/calibration can be toggled.

### Limitations
- Does not use xG, player‑level data, or lineups by default.
- Odds are only as good as the provider and match coverage.
- Injury adjustments are coarse unless you supply a rich dataset.

---

## 9) Where to Improve Next
- Add xG or shot‑based features.
- Build a player‑aware model for lineups and injuries.
- Learn optimal scoreline distributions (e.g., NegBin or neural net).
- Use deeper calibration (temperature scaling, isotonic regression).
