from __future__ import annotations

import json
import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import jsonschema


def _env() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    return env


def test_strategy_cli_smoke(tmp_path: Path):
    snapshot_path = Path("tests/fixtures/regime_snapshot_golden.json")
    cfg_path = Path("config/strategy_v1.yaml")
    out_path = tmp_path / "strategy.json"

    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "strategy",
        "--snapshot",
        str(snapshot_path),
        "--cfg",
        str(cfg_path),
        "--out",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    schema = json.loads(
        Path("contracts/regime_strategy.schema.v1.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(payload, schema)

    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert payload["snapshot_id"] == snapshot["snapshot_id"]
    assert payload["as_of_ts"] == snapshot["as_of_ts"]

    cfg_hash = sha256(cfg_path.read_bytes()).hexdigest()
    assert payload["config_hash"] == cfg_hash
