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
    odds_model: LogisticRegression | None = None

    def predict_probs(
        self,
        *,
        p_dc,
        p_elo,
        p_book,
    ):
        model = self.model
        order = self.feature_order
        if p_book is not None and self.odds_model is not None:
            model = self.odds_model
            order += ("book_h", "book_d", "book_a")
        feats = _feature_row(p_dc=p_dc, p_elo=p_elo, p_book=p_book, order=order)
        p = np.zeros(3)
        p[model.classes_.astype(int)] = model.predict_proba(feats.reshape(1, -1))[0]
        return float(p[0]), float(p[1]), float(p[2])


def train_outcome_calibrator(
    rows,
    *,
    use_odds_features=True,
    max_iter=2000,
):
    feature_order = ["dc_h", "dc_d", "dc_a", "elo_h", "elo_d", "elo_a"]
    X = rows[feature_order].to_numpy(dtype=float)
    y = rows["y"].to_numpy(dtype=int)
    if len(np.unique(y)) < 2 or not np.isfinite(X).all():
        raise ValueError("Calibration needs finite features and at least two outcome classes.")
    model = LogisticRegression(
        max_iter=max_iter,
        solver="lbfgs",
    )
    model.fit(X, y)
    odds_model = None
    book_columns = ["book_h", "book_d", "book_a"]
    if use_odds_features and set(book_columns).issubset(rows.columns):
        available = np.isfinite(rows[book_columns].to_numpy(dtype=float)).all(axis=1)
        if available.sum() >= 30 and rows.loc[available, "y"].nunique() >= 2:
            odds_model = LogisticRegression(max_iter=max_iter, solver="lbfgs")
            odds_model.fit(rows.loc[available, feature_order + book_columns], y[available])
    return OutcomeCalibrator(model=model, feature_order=tuple(feature_order), odds_model=odds_model)


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
        "book_h": float(p_book[0]) if p_book is not None else 1.0 / 3.0,
        "book_d": float(p_book[1]) if p_book is not None else 1.0 / 3.0,
        "book_a": float(p_book[2]) if p_book is not None else 1.0 / 3.0,
    }
    return np.array([mapping[c] for c in order], dtype=float)
