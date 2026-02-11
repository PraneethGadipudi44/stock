from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _env() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    return env


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n")


def test_tune_explain_summary_lock(tmp_path: Path):
    cfg = Path("tests/fixtures/regime_test_cfg.yaml")
    out_csv = tmp_path / "tune.csv"
    out_explain = tmp_path / "explain.json"

    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "tune",
        "--cfg",
        str(cfg),
        "--out",
        str(out_csv),
        "--explain",
        str(out_explain),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr

    expected = _normalize(
        Path("tests/fixtures/tune_explain_summary_golden.json").read_text(
            encoding="utf-8"
        )
    )
    actual = _normalize(out_explain.read_text(encoding="utf-8"))
    assert actual == expected
