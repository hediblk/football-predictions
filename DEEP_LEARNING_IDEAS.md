# Deep Learning Ideas for Football (1X2 + Season Positions)

This project already uses probabilistic match models + Monte Carlo season simulation. Deep learning can replace (or augment) the match-probability layer, then the rest of the pipeline (simulating remaining fixtures and aggregating final positions) stays the same.

## What Deep Learning Would Predict

You typically want one of these outputs per match:
- **1X2 probabilities**: `P(home win), P(draw), P(away win)` (directly optimizes log loss).
- **Score distribution**: a full `P(home_goals, away_goals)` grid, or distribution parameters (e.g., Poisson / NegBin means).
- **Expected goals**: `λ_home, λ_away` (then derive 1X2 from a goal model).

For season-position probabilities:
1) Use the model to predict each remaining fixture.
2) Simulate the season many times (same as now).

## Inputs That Actually Help

Deep learning only wins if you feed it richer signals than “goals and results”.

High-value inputs (in roughly descending order of impact, if you can source them):
- **Closing odds** (multiple books, exchanges) and line movement.
- **xG and shot data** (team + player), shot quality breakdowns.
- **Lineups and minutes** (who started, substitutions, minutes played).
- **Injuries/suspensions** with player value proxies (minutes share, xG+xA, defensive actions).
- **Rest days / congestion / travel**, schedule difficulty, weather.
- **Manager changes**, transfers, tactical proxies (pressing intensity, possession, etc.).

## Model Families That Fit This Problem

### 1) Tabular neural nets (fastest to start)
- Start with the same engineered features you’d use for sklearn (form, Elo, DC expected goals, odds).
- A small MLP can learn non-linear interactions (e.g., “draws rise when teams are similar + low total xG”).
- Often competitive, but gradient-boosted trees frequently win on pure tabular data unless you add sequence/player inputs.

### 2) Team-history sequence models (captures “form” end-to-end)
- Represent each team as a sequence of its last N matches with per-match features.
- Use a Transformer/GRU to encode each team history into an embedding.
- Combine (home_embedding, away_embedding, context features) -> predict 1X2 or (λ_home, λ_away).

Practical note: do strict time splits; otherwise you’ll leak future info through sequences.

### 3) Player-aware models (usually the biggest edge, hardest data)
- Encode the **expected lineup** as a set (DeepSets) or graph (players connected by team/position).
- Aggregate to team strength conditioned on who plays.
- This is where injury/rotation effects become “learned” rather than hand-tuned.

### 4) Graph neural networks over a match graph
- Nodes: teams (and optionally players).
- Edges: matches (with features like venue, xG, cards, etc.).
- Learns interaction structure and can handle asymmetric effects (home vs away).

## Training Objectives & Calibration

If you want bookmaker-level usefulness, calibration matters as much as accuracy.
- Use **log loss** as the primary metric for 1X2.
- Add **calibration checks** (reliability curves, ECE) and consider temperature scaling.
- For score models, train with **proper likelihoods** (Poisson/NegBin) rather than MSE on goals.

## Avoiding Data Leakage (Critical)

Typical leakage traps:
- Using season-end features (final points, final rank) during training.
- Using rolling features that accidentally include the match being predicted.
- Training/evaluating with random splits instead of time-based splits.

Best practice:
- Use **rolling-origin evaluation**: train on past, predict the next window.

## How It Plugs Into This Repo

Recommended approach for next iterations:
1) Keep the current simulation + table output unchanged.
2) Swap `match probability provider`:
   - baseline: Dixon–Coles / Elo / odds blend
   - deep model: `predict_match_probs(home, away, context)` (and optionally expected goals)
3) Backtest on past seasons and compare log loss + calibration.

## Minimal Next Step (If You Want a DL Prototype)

If you can provide xG + lineup/minutes data:
- Build a dataset of matches with:
  - team history tensors (last N matches per team)
  - lineup embeddings (optional)
  - odds features (optional)
- Train a small Transformer to predict 1X2 probabilities.
- Calibrate and then feed predictions into the same season simulator.

