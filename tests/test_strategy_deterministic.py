from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _env() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    return env


def _run_strategy(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    snapshot = Path("tests/fixtures/regime_snapshot_golden.json")
    cfg = Path("config/strategy_v1.yaml")
    out_path = tmp_path / "strategy.json"
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "strategy",
        "--snapshot",
        str(snapshot),
        "--cfg",
        str(cfg),
        "--out",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr
    return out_path


def test_strategy_deterministic(tmp_path: Path):
    a = _run_strategy(tmp_path / "a")
    b = _run_strategy(tmp_path / "b")
    assert a.read_bytes() == b.read_bytes()
