from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _env() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    return env


def _run_replay(tmp_path: Path) -> tuple[Path, Path]:
    cfg = Path("tests/fixtures/regime_test_cfg.yaml")
    prices = Path("tests/fixtures/prices_replay_long.csv")
    store = tmp_path / "store"
    out_csv = tmp_path / "replay.csv"
    explain_dir = tmp_path / "explain"

    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "replay",
        "--cfg",
        str(cfg),
        "--prices",
        str(prices),
        "--store",
        str(store),
        "--start",
        "2026-01-16",
        "--end",
        "2026-01-20",
        "--out",
        str(out_csv),
        "--explain-dir",
        str(explain_dir),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr
    return out_csv, explain_dir


def test_replay_explain_deterministic(tmp_path: Path):
    out_a, explain_a = _run_replay(tmp_path / "a")
    out_b, explain_b = _run_replay(tmp_path / "b")

    assert out_a.read_bytes() == out_b.read_bytes()

    files_a = sorted(explain_a.glob("*.explain.json"))
    files_b = sorted(explain_b.glob("*.explain.json"))
    assert [f.name for f in files_a] == [f.name for f in files_b]
    assert len(files_a) == 5
    for a_file, b_file in zip(files_a, files_b):
        assert a_file.read_bytes() == b_file.read_bytes()
