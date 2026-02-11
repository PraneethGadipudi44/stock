from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import jsonschema


def _env() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    return env


def test_explain_schema_lock():
    schema_path = Path("contracts/regime_explain.schema.v1.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert schema["$id"].endswith("regime_explain.schema.v1.json")

    base = schema["$defs"]["BaseExplain"]
    expected_required = {
        "schema_version",
        "snapshot_id",
        "snapshot_schema_version",
        "as_of_ts",
        "engine_version",
        "config_source",
        "config_hash",
        "metrics",
        "signal_votes",
        "confidence_breakdown",
    }
    assert set(base["required"]) == expected_required
    assert base["properties"]["schema_version"]["const"] == 1


def test_explain_schema_validates_snapshot_and_tune_outputs(tmp_path: Path):
    schema_path = Path("contracts/regime_explain.schema.v1.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    cfg = Path("tests/fixtures/regime_test_cfg.yaml")
    prices = Path("tests/fixtures/prices_small.csv")
    snapshot_out = tmp_path / "snapshot.json"
    explain_out = tmp_path / "explain.json"

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
        str(snapshot_out),
        "--explain",
        str(explain_out),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr
    explain_payload = json.loads(explain_out.read_text(encoding="utf-8"))
    jsonschema.validate(explain_payload, schema)

    tune_out = tmp_path / "tune.csv"
    explain_dir = tmp_path / "explain_dir"
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "tune",
        "--cfg",
        str(cfg),
        "--out",
        str(tune_out),
        "--explain-dir",
        str(explain_dir),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr
    explain_files = sorted(explain_dir.glob("*.explain.json"))
    assert explain_files, "Expected tune explain files."
    explain_payload = json.loads(explain_files[0].read_text(encoding="utf-8"))
    jsonschema.validate(explain_payload, schema)
