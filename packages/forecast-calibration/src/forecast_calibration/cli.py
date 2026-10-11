from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path

import pandas as pd

from forecast_calibration.dataset import CALIBRATION_LEAGUES, ROBUSTNESS_LEAGUES, XG_GRID, build_dataset
from forecast_calibration.fit import calibrate


def _read_dataset(path):
    metadata = json.loads(path.with_suffix(".json").read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest() != metadata["sha256"]:
        raise ValueError("Dataset checksum does not match its metadata.")
    return pd.read_csv(path), metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build prior-only multi-league forecasts and fit one fixed set of global weights.")
    parser.add_argument("--leagues", nargs="+", default=list(CALIBRATION_LEAGUES))
    parser.add_argument("--robustness-leagues", nargs="*", default=list(ROBUSTNESS_LEAGUES))
    parser.add_argument("--seasons", nargs="+", type=int, default=list(range(2015, 2026)))
    parser.add_argument("--xg-grid", nargs="+", type=float, default=list(XG_GRID))
    parser.add_argument("--prior-seasons", type=int, default=2)
    parser.add_argument("--xi", type=float, default=0.003)
    parser.add_argument("--lambda-reg", type=float, default=0.1)
    parser.add_argument("--holdout-seasons", type=int, default=2)
    parser.add_argument("--out-dir", type=Path, default=Path("out/global-calibration"))
    parser.add_argument("--dataset", type=Path, help="Reuse an existing dataset.csv and its dataset.json; skip building.")
    parser.add_argument("--robustness-dataset", type=Path)
    parser.add_argument("--weights-out", type=Path, help="Also save the artifact here, e.g. src/standing_prediction/calibrated_weights.json.")
    parser.add_argument("--cache", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    options = {key: getattr(args, key) for key in ("seasons", "prior_seasons", "xi", "lambda_reg", "cache")}
    if args.dataset:
        frame, metadata = _read_dataset(args.dataset)
    else:
        frame, metadata = build_dataset(leagues=args.leagues, out_dir=args.out_dir / "features", xg_grid=args.xg_grid, **options)
    robustness, robustness_metadata = None, None
    if args.robustness_dataset:
        robustness, robustness_metadata = _read_dataset(args.robustness_dataset)
    elif not args.dataset and args.robustness_leagues:
        robustness, robustness_metadata = build_dataset(leagues=args.robustness_leagues, out_dir=args.out_dir / "robustness", xg_grid=metadata["xg_grid"], **options)
    report = calibrate(frame, metadata, robustness=robustness, robustness_metadata=robustness_metadata, holdout_seasons=args.holdout_seasons)
    content = json.dumps(report, indent=2, allow_nan=False) + "\n"
    (args.out_dir / "calibrated_weights.json").write_text(content)
    if args.weights_out:
        args.weights_out.parent.mkdir(parents=True, exist_ok=True)
        args.weights_out.write_text(content)
    print(json.dumps({key: report[key] for key in ("version", "weights", "no_odds_weights", "xg_weight", "metrics", "chronological_holdout")}, indent=2))
    print(f"Saved calibration to {args.out_dir / 'calibrated_weights.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
