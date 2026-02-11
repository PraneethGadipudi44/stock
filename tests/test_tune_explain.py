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


def _run_tune(tmp_path: Path) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    cfg = Path("tests/fixtures/regime_test_cfg.yaml")
    out_csv = tmp_path / "tune.csv"
    explain_dir = tmp_path / "explain"

    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "tune",
        "--cfg",
        str(cfg),
        "--out",
        str(out_csv),
        "--explain-dir",
        str(explain_dir),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr
    return out_csv, explain_dir


def test_tune_explain_deterministic(tmp_path: Path):
    out_a, explain_a = _run_tune(tmp_path / "a")
    out_b, explain_b = _run_tune(tmp_path / "b")

    assert out_a.read_bytes() == out_b.read_bytes()

    files_a = sorted(explain_a.glob("*.explain.json"))
    files_b = sorted(explain_b.glob("*.explain.json"))
    assert [f.name for f in files_a] == [f.name for f in files_b]
    assert len(files_a) == len(files_b)
    for a_file, b_file in zip(files_a, files_b):
        assert a_file.read_bytes() == b_file.read_bytes()

    row_count = len(out_a.read_text(encoding="utf-8").splitlines()) - 1
    assert row_count == len(files_a)


def test_tune_explain_contains_required_keys(tmp_path: Path):
    _, explain_dir = _run_tune(tmp_path / "c")
    files = sorted(explain_dir.glob("*.explain.json"))
    assert files, "Expected explain files to be written."
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert "scenario" in payload
    assert "snapshot" in payload
    assert "confidence_breakdown" in payload
