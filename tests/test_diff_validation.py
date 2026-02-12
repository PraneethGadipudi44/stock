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


def _run_diff(prev_path: Path, curr_path: Path, out_path: Path) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "diff",
        "--prev",
        str(prev_path),
        "--curr",
        str(curr_path),
        "--out",
        str(out_path),
    ]
    return subprocess.run(cmd, capture_output=True, text=True, env=_env())


def test_diff_validation_mismatched_schema(tmp_path: Path):
    prev_path = Path("tests/fixtures/regime_snapshot_prices_golden.json")
    curr_payload = json.loads(
        Path("tests/fixtures/regime_snapshot_golden.json").read_text(encoding="utf-8")
    )
    curr_payload["schema_version"] = 2
    curr_path = tmp_path / "curr.json"
    curr_path.write_text(json.dumps(curr_payload), encoding="utf-8")

    out_path = tmp_path / "diff.json"
    result = _run_diff(prev_path, curr_path, out_path)
    assert result.returncode == 2
    assert "Snapshot schema versions must match" in result.stderr


def test_diff_validation_same_snapshot_id(tmp_path: Path):
    prev_payload = json.loads(
        Path("tests/fixtures/regime_snapshot_prices_golden.json").read_text(
            encoding="utf-8"
        )
    )
    curr_payload = json.loads(
        Path("tests/fixtures/regime_snapshot_golden.json").read_text(
            encoding="utf-8"
        )
    )
    curr_payload["snapshot_id"] = prev_payload["snapshot_id"]
    curr_path = tmp_path / "curr.json"
    curr_path.write_text(json.dumps(curr_payload), encoding="utf-8")

    out_path = tmp_path / "diff.json"
    result = _run_diff(Path("tests/fixtures/regime_snapshot_prices_golden.json"), curr_path, out_path)
    assert result.returncode == 2
    assert "Snapshot IDs must differ" in result.stderr


def test_diff_validation_ordering(tmp_path: Path):
    prev_path = Path("tests/fixtures/regime_snapshot_golden.json")
    curr_path = Path("tests/fixtures/regime_snapshot_prices_golden.json")
    out_path = tmp_path / "diff.json"

    result = _run_diff(prev_path, curr_path, out_path)
    assert result.returncode == 2
    assert "as_of_ts ordering must be prev < curr" in result.stderr
