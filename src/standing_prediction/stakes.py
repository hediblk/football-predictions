"""What's at stake: how each result of an upcoming fixture moves every team's title, top-four and relegation odds.

The season simulation records each tracked fixture's simulated result and every team's finishing place;
conditioning on a result is just filtering those simulations, so it costs no extra runs.
"""

from __future__ import annotations

import numpy as np

from standing_prediction.site_history import chance

# Fewer simulations behind a result make its conditional chances too noisy to show.
MIN_SIMS = 200
# With 10,000 simulations a 50% chance conditioned on a 25% draw (2,500 sims) has a Monte Carlo standard error
# of about 1 point, so a swing under 2 points is indistinguishable from noise.
MIN_SWING = 2.0


def fixture_stakes(outcomes, places, teams, *, top, releg_from, min_swing=MIN_SWING):
    """Per tracked fixture: simulations per result and each team's conditional chances, in percent.

    `outcomes` (n_sim, n_fixtures) holds 0 home win / 1 draw / 2 away win and `places` (n_sim, n_teams) the
    zero-based finishing place. Chances are title (place 0), `ucl` (best `top`) and `releg` (`releg_from`
    onwards, one-based). A metric is kept only if it swings by at least `min_swing` points (and 3 standard errors) across results,
    and a team only if it keeps one; a result with fewer than MIN_SIMS simulations is None.
    """
    events = {"title": places == 0, "ucl": places < top, "releg": places >= releg_from - 1}
    return event_stakes(outcomes, events, teams, min_swing=min_swing)


# `fixture_stakes` for any chances: `events` maps each metric to a (n_sim, n_teams) boolean array.
def event_stakes(outcomes, events, teams, *, min_swing=MIN_SWING):
    stakes = []
    for f in range(outcomes.shape[1]):
        masks = [outcomes[:, f] == o for o in range(3)]
        counts = [int(mask.sum()) for mask in masks]
        chances = {metric: [event[mask].mean(axis=0) * 100 if n >= MIN_SIMS else None for mask, n in zip(masks, counts)]
                   for metric, event in events.items()}
        out = {}
        for t, team in enumerate(teams):
            kept = {}
            for metric, values in chances.items():
                known = [o for o, v in enumerate(values) if v is not None]
                if len(known) < 2:
                    continue
                a, b = max(known, key=lambda o: values[o][t]), min(known, key=lambda o: values[o][t])
                p = events[metric][:, t].mean()
                # Keep a swing only if it is 3 standard errors of the difference between the two conditional
                # chances, so teams the fixture doesn't touch don't show Monte Carlo noise.
                se = 100 * np.sqrt(p * (1 - p) * (1 / counts[a] + 1 / counts[b]))
                if values[a][t] - values[b][t] >= max(min_swing, 3 * se):
                    kept[metric] = [None if v is None else chance(v[t]) for v in values]
            if kept:
                out[team] = kept
        stakes.append({"n": counts, "teams": out})
    return stakes
