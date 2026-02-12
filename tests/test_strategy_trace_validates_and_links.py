from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _env() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    return env


def _run_snapshot_with_explain(tmp_path: Path) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    cfg = Path("tests/fixtures/regime_test_cfg.yaml")
    prices = Path("tests/fixtures/prices_small.csv")
    snapshot_path = tmp_path / "snapshot.json"
    explain_path = tmp_path / "explain.json"

    cmd = [
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
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr
    return snapshot_path, explain_path


def _run_strategy(snapshot_path: Path, tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    out_path = tmp_path / "strategy.json"
    cfg = Path("config/strategy_v1.yaml")
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "strategy",
        "--snapshot",
        str(snapshot_path),
        "--cfg",
        str(cfg),
        "--schema-version",
        "2",
        "--out",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr
    return out_path


def _run_trace(strategy_path: Path, explain_path: Path, tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    out_path = tmp_path / "trace.json"
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "trace",
        "--strategy",
        str(strategy_path),
        "--explain",
        str(explain_path),
        "--out",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr
    return out_path


def test_strategy_trace_validates_and_links(tmp_path: Path):
    snapshot_path, explain_path = _run_snapshot_with_explain(tmp_path / "snap")
    strategy_path = _run_strategy(snapshot_path, tmp_path / "strat")
    trace_path = _run_trace(strategy_path, explain_path, tmp_path / "trace")

    trace_payload = json.loads(trace_path.read_text(encoding="utf-8"))
    strategy_payload = json.loads(strategy_path.read_text(encoding="utf-8"))
    explain_payload = json.loads(explain_path.read_text(encoding="utf-8"))

    assert trace_payload["snapshot_id"] == strategy_payload["snapshot_id"]
    assert trace_payload["snapshot_id"] == explain_payload["snapshot_id"]
    assert trace_payload["as_of_ts"] == strategy_payload["as_of_ts"]
    assert trace_payload["as_of_ts"] == explain_payload["as_of_ts"]
    assert trace_payload["strategy_schema_version"] == strategy_payload["schema_version"]
    assert trace_payload["explain_schema_version"] == explain_payload["schema_version"]


def test_strategy_trace_snapshot_id_mismatch_fails(tmp_path: Path):
    snapshot_path, explain_path = _run_snapshot_with_explain(tmp_path / "snap")
    strategy_path = _run_strategy(snapshot_path, tmp_path / "strat")

    bad_explain = json.loads(explain_path.read_text(encoding="utf-8"))
    bad_explain["snapshot_id"] = "mismatch"
    bad_explain_path = tmp_path / "bad_explain.json"
    bad_explain_path.write_text(json.dumps(bad_explain), encoding="utf-8")

    out_path = tmp_path / "trace.json"
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "trace",
        "--strategy",
        str(strategy_path),
        "--explain",
        str(bad_explain_path),
        "--out",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 2
    assert "Snapshot ID mismatch" in result.stderr
