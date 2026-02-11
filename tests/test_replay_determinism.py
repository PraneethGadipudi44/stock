from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _env() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    return env


def test_replay_deterministic_twice(tmp_path: Path):
    cfg = Path("tests/fixtures/regime_test_cfg.yaml")
    prices = Path("tests/fixtures/prices_replay_long.csv")

    store_a = tmp_path / "store_a"
    store_b = tmp_path / "store_b"
    out_a = tmp_path / "replay_a.csv"
    out_b = tmp_path / "replay_b.csv"

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
        str(store_a),
        "--start",
        "2026-01-16",
        "--end",
        "2026-01-20",
        "--out",
        str(out_a),
    ]
    result_a = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result_a.returncode == 0

    cmd[cmd.index(str(store_a))] = str(store_b)
    cmd[cmd.index(str(out_a))] = str(out_b)
    result_b = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result_b.returncode == 0

    assert out_a.read_bytes() == out_b.read_bytes()