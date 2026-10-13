import json
from pathlib import Path

import numpy as np

_path = Path(__file__).with_name("calibrated_weights.json")
CALIBRATION = json.loads(_path.read_text()) if _path.exists() else {}
DEFAULT_WEIGHTS = CALIBRATION.get("weights", {"main": 0.35, "odds": 0.55, "elo": 0.10})
DEFAULT_XG_WEIGHT = CALIBRATION.get("xg_weight", 0.0)
DEFAULT_XG_SCALE = CALIBRATION.get("xg_scale", 1.0)
CALIBRATION_VERSION = CALIBRATION.get("version")
DEFAULT_FIT = CALIBRATION.get("fit_settings", {"xi": 0.003, "lambda_reg": 0.1, "prior_seasons": 2})

if (set(DEFAULT_WEIGHTS) != {"main", "odds", "elo"}
        or any(not np.isfinite(w) or w < 0 for w in DEFAULT_WEIGHTS.values())
        or not np.isclose(sum(DEFAULT_WEIGHTS.values()), 1)
        or DEFAULT_WEIGHTS["main"] + DEFAULT_WEIGHTS["elo"] <= 0
        or not 0 <= DEFAULT_XG_WEIGHT <= 1
        or not np.isfinite(DEFAULT_XG_SCALE) or DEFAULT_XG_SCALE <= 0):
    raise ValueError("Invalid calibrated forecast defaults.")
