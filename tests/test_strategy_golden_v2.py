from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _env() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    return env


def test_strategy_golden_v2(tmp_path: Path):
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
        "--schema-version",
        "2",
        "--out",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr

    expected = Path("tests/fixtures/strategy_golden_v2.json").read_text(
        encoding="utf-8"
    )
    actual = out_path.read_text(encoding="utf-8")
    assert actual == expected
