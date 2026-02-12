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


def _run_strategy(tmp_path: Path, version: int) -> dict:
    tmp_path.mkdir(parents=True, exist_ok=True)
    snapshot_path = Path("tests/fixtures/regime_snapshot_golden.json")
    cfg_path = Path("config/strategy_v1.yaml")
    out_path = tmp_path / f"strategy_v{version}.json"

    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "strategy",
        "--snapshot",
        str(snapshot_path),
        "--cfg",
        str(cfg_path),
        "--schema-version",
        str(version),
        "--out",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr
    return json.loads(out_path.read_text(encoding="utf-8"))


def test_strategy_v2_regime_config_hash_nullable(tmp_path: Path):
    payload = _run_strategy(tmp_path, 2)
    assert payload["regime_config_hash"] is None
    assert "guardrail.missing_regime_config_hash" in payload["guardrails"]


def test_strategy_cli_schema_version_flag_roundtrip(tmp_path: Path):
    payload_v1 = _run_strategy(tmp_path / "v1", 1)
    payload_v2 = _run_strategy(tmp_path / "v2", 2)

    schema_v1 = json.loads(
        Path("contracts/regime_strategy.schema.v1.json").read_text(encoding="utf-8")
    )
    schema_v2 = json.loads(
        Path("contracts/regime_strategy.schema.v2.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(payload_v1, schema_v1)
    jsonschema.validate(payload_v2, schema_v2)

    assert payload_v1["schema_version"] == 1
    assert payload_v2["schema_version"] == 2
    assert "config_hash" in payload_v1
    assert "regime_config_hash" in payload_v2
