from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _env() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    return env


def test_loads_user_cfg_when_provided(tmp_path: Path):
    cfg = Path("tests/fixtures/regime_test_cfg.yaml")
    prices = Path("tests/fixtures/prices_small.csv")
    out_path = tmp_path / "out.json"

    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "--debug",
        "snapshot",
        "--cfg",
        str(cfg),
        "--prices",
        str(prices),
        "--out",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0
    assert f"Using config: {cfg}" in result.stderr


def test_falls_back_to_packaged_cfg(tmp_path: Path):
    prices = Path("tests/fixtures/prices_replay_long.csv")
    out_path = tmp_path / "out.json"

    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "--debug",
        "snapshot",
        "--prices",
        str(prices),
        "--out",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0
    assert "Using packaged config resource." in result.stderr