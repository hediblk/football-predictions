import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("mode", ["publish", "reject", "all-fail"])
def test_refresh_publishes_only_a_valid_candidate(tmp_path, mode):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy(Path(__file__).resolve().parents[1] / "scripts/refresh_site.sh", scripts)
    data = tmp_path / "site/data"
    data.mkdir(parents=True)
    (data / "updated.txt").write_text("old")
    (data / "retained.txt").write_text("previous competition")
    commands = tmp_path / "bin"
    commands.mkdir()
    stubs = {
        "sleep": "exit 0\n",
        "football-predict": '''[ "$MODE" != all-fail ] || exit 1
if [ "$2" = PL ]; then
  printf partial > out/site/pl_summary.csv
  printf partial > out/site/pl_metadata.json
  exit 1
fi
''',
        "football-ucl": '[ "$MODE" != all-fail ]\n',
        "python": '''case "$1" in
  scripts/build_site_data.py)
    while [ "$1" != --dest ]; do shift; done
    printf fresh > "$2/updated.txt"
    printf build >> calls
    ;;
  scripts/validate_site_data.py)
    [ "$(cat "$3/updated.txt")" = fresh ] || exit 2
    printf validate >> calls
    [ "$MODE" != reject ]
    ;;
  *) exit 2 ;;
esac
''',
    }
    for name, body in stubs.items():
        path = commands / name
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)
    env = {**os.environ, "PATH": f"{commands}:{os.environ['PATH']}", "MODE": mode}
    result = subprocess.run(["bash", str(scripts / "refresh_site.sh")], env=env, capture_output=True, text=True)
    assert result.returncode == (0 if mode == "publish" else 1), result.stderr
    assert (data / "updated.txt").read_text() == ("fresh" if mode == "publish" else "old")
    assert (data / "retained.txt").read_text() == "previous competition"
    assert not (tmp_path / "out/site/pl_summary.csv").exists()
    assert not (tmp_path / "out/site/pl_metadata.json").exists()
    if mode == "all-fail":
        assert not (tmp_path / "calls").exists()
    else:
        assert (tmp_path / "calls").read_text() == "buildvalidate"
