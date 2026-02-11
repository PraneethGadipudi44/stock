from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _env() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    return env


def test_replay_golden_lock(tmp_path: Path):
    cfg = Path("tests/fixtures/regime_test_cfg.yaml")
    prices = Path("tests/fixtures/prices_replay_long.csv")
    expected = Path("tests/fixtures/replay_golden.csv").read_bytes()

    store_dir = tmp_path / "store"
    out_path = tmp_path / "replay.csv"

    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "replay",
        "--cfg",
        str(cfg),
        "--prices",
        str(prices),
        "--store",
        str(store_dir),
        "--start",
        "2026-01-16",
        "--end",
        "2026-01-20",
        "--out",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr

    assert out_path.read_bytes() == expected
