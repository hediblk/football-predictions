from __future__ import annotations

import numpy as np


def blend_probabilities(
    p_main,
    *,
    p_odds=None,
    p_elo=None,
    weights=None,
    eps=1e-12,
):
    w = {"main": 1.0, "odds": 0.0, "elo": 0.0}
    if weights:
        w.update(weights)

    parts = []
    part_weights = []

    def add_part(key, p):
        if p is None:
            return
        weight = float(w.get(key, 0.0))
        if weight <= 0:
            return
        parts.append(np.log(np.clip(np.array(p, dtype=float), eps, 1.0)))
        part_weights.append(weight)

    add_part("main", p_main)
    add_part("odds", p_odds)
    add_part("elo", p_elo)

    if not parts:
        return 1 / 3, 1 / 3, 1 / 3

    ww = np.array(part_weights, dtype=float)
    ww = ww / ww.sum()
    log_p = np.tensordot(ww, np.stack(parts, axis=0), axes=1)
    p = np.exp(log_p)
    p = p / p.sum()
    return float(p[0]), float(p[1]), float(p[2])
