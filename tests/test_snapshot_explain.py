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


def _run_snapshot_explain(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    cfg = Path("tests/fixtures/regime_test_cfg.yaml")
    prices = Path("tests/fixtures/prices_small.csv")
    out_json = tmp_path / "snapshot.json"
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
        str(out_json),
        "--explain",
        str(explain_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr
    return explain_path


def test_snapshot_explain_deterministic(tmp_path: Path):
    explain_a = _run_snapshot_explain(tmp_path / "a")
    explain_b = _run_snapshot_explain(tmp_path / "b")
    assert explain_a.read_bytes() == explain_b.read_bytes()


def test_snapshot_explain_contains_required_keys(tmp_path: Path):
    explain_path = _run_snapshot_explain(tmp_path / "c")
    payload = json.loads(explain_path.read_text(encoding="utf-8"))

    required_keys = {
        "snapshot_id",
        "snapshot_schema_version",
        "as_of_ts",
        "as_of_date",
        "session",
        "engine_version",
        "config_source",
        "config_hash",
        "inputs_hash",
        "benchmarks",
        "metrics",
        "metrics_snapshot",
        "signal_votes",
        "market_phase",
        "trend_regime",
        "vol_regime",
        "risk_tone",
        "confidence_breakdown",
        "regime_changed",
        "change_reason",
        "change_drivers",
        "previous_snapshot_id",
    }
    assert required_keys.issubset(payload.keys())
