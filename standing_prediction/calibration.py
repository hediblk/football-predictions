from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression


@dataclass(frozen=True)
class OutcomeCalibrator:
    model: LogisticRegression
    feature_order: Tuple[str, ...]

    def predict_probs(
        self,
        *,
        p_dc,
        p_elo,
        p_book,
    ):
        feats = _feature_row(p_dc=p_dc, p_elo=p_elo, p_book=p_book, order=self.feature_order)
        p = self.model.predict_proba(feats.reshape(1, -1))[0]
        return float(p[0]), float(p[1]), float(p[2])


def train_outcome_calibrator(
    rows,
    *,
    use_odds_features=True,
    max_iter=2000,
):
    """
    Train a multinomial logistic regression that maps base model probabilities
    (DC, Elo, and optionally odds) -> calibrated 1X2 probabilities.

    Expected columns in `rows`:
      - y (int: 0/1/2)
      - dc_h, dc_d, dc_a
      - elo_h, elo_d, elo_a
      - book_h, book_d, book_a (optional; can be NaN)
    """
    feature_order = ["dc_h", "dc_d", "dc_a", "elo_h", "elo_d", "elo_a"]
    if use_odds_features:
        feature_order += ["book_h", "book_d", "book_a"]

    X = rows[feature_order].to_numpy(dtype=float)
    if use_odds_features:
        # Fill missing odds with neutral priors.
        X[:, -3:] = np.where(np.isfinite(X[:, -3:]), X[:, -3:], 1.0 / 3.0)

    y = rows["y"].to_numpy(dtype=int)

    model = LogisticRegression(
        max_iter=max_iter,
        solver="lbfgs",
    )
    model.fit(X, y)
    return OutcomeCalibrator(model=model, feature_order=tuple(feature_order))


def _feature_row(
    *,
    p_dc,
    p_elo,
    p_book,
    order,
):
    mapping = {
        "dc_h": float(p_dc[0]),
        "dc_d": float(p_dc[1]),
        "dc_a": float(p_dc[2]),
        "elo_h": float(p_elo[0]),
        "elo_d": float(p_elo[1]),
        "elo_a": float(p_elo[2]),
        "book_h": float(p_book[0]) if p_book else 1.0 / 3.0,
        "book_d": float(p_book[1]) if p_book else 1.0 / 3.0,
        "book_a": float(p_book[2]) if p_book else 1.0 / 3.0,
    }
    return np.array([mapping[c] for c in order], dtype=float)
