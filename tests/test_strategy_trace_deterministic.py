from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _env() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    return env


def _run_trace(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    cfg = Path("tests/fixtures/regime_test_cfg.yaml")
    prices = Path("tests/fixtures/prices_small.csv")
    snapshot_path = tmp_path / "snapshot.json"
    explain_path = tmp_path / "explain.json"
    strategy_path = tmp_path / "strategy.json"
    trace_path = tmp_path / "trace.json"

    cmd_snapshot = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "snapshot",
        "--cfg",
        str(cfg),
        "--prices",
        str(prices),
        "--out",
        str(snapshot_path),
        "--explain",
        str(explain_path),
    ]
    result = subprocess.run(cmd_snapshot, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr

    cmd_strategy = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "strategy",
        "--snapshot",
        str(snapshot_path),
        "--cfg",
        str(Path("config/strategy_v1.yaml")),
        "--schema-version",
        "2",
        "--out",
        str(strategy_path),
    ]
    result = subprocess.run(cmd_strategy, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr

    cmd_trace = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "trace",
        "--strategy",
        str(strategy_path),
        "--explain",
        str(explain_path),
        "--out",
        str(trace_path),
    ]
    result = subprocess.run(cmd_trace, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr

    return trace_path


def test_strategy_trace_deterministic(tmp_path: Path):
    trace_a = _run_trace(tmp_path / "a")
    trace_b = _run_trace(tmp_path / "b")
    assert trace_a.read_bytes() == trace_b.read_bytes()
