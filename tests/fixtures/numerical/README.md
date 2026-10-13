# Frozen numerical cases

These invented clubs and results are test inputs, not football observations. Files are checked in;
tests never generate or fetch them. The creation seed was 9173. Results were sampled once from
Poisson rates with unequal club strengths; xG values vary around those rates, with some missing.

- `domestic.json`: eight clubs, two complete prior seasons and a partially played double round robin.
  Eight remaining matches have timestamped odds; the other sixteen exercise the goal/xG/Elo blend.
- `ucl.json`: 36 clubs in three connected domestic leagues, domestic and European history, and the
  full 144-match league schedule. Four rounds are finished. Each club has eight distinct opponents
  and four home/four away matches. Twelve archived quotes influence the strength fit; no direct
  fixture odds enter the tournament simulation. Coefficients are frozen too.
- `*_baseline.json`: reviewed raw match/score probabilities, goal rates, position probabilities,
  expected points/positions and event/stage chances. Configuration, input hash, numerical dependency
  versions, platform, Python version, seed, simulation count and generating revision accompany them.

Baselines were initially generated on macOS with Python 3.12 and the pinned dependencies; repeated
public-API runs agreed exactly locally, and Linux CI (Ubuntu 24.04) matches them within the
tolerances. The generating revision identifies the source
checkout before these uncommitted test artifacts were added.

The test module injects frozen provider inputs into both public forecast APIs, blocks network access,
and skips rendering. It exercises the real fitting, forecast, simulation, summary and match-output
functions. Daily flags and CLI/API defaults are checked against the stored configuration.

Tests never write baselines. For an intentional, explained update, run this explicitly from the
repository root in the chosen environment, review the resulting diff and rerun the tests:

```bash
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONHASHSEED=0 .venv/bin/python - <<'PY'
import importlib.util
import json
from pathlib import Path
import tempfile
import pytest

spec = importlib.util.spec_from_file_location("numerical", "tests/test_numerical_regression.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
for name in ("domestic", "ucl"):
    with tempfile.TemporaryDirectory() as output, pytest.MonkeyPatch.context() as patch:
        actual = module.run_case(name, Path(output), patch)
        baseline = {"provenance": module.provenance(name), "payload": actual["payload"]}
        path = module.FIXTURES / f"{name}_baseline.json"
        path.write_text(json.dumps(baseline, indent=1) + "\n")
PY
```

See [numerical protection](../../../docs/numerical-protection.md) for thresholds, invariants,
timing rules, baseline review and the limits of this coverage.
