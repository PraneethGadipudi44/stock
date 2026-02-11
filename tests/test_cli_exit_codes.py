from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _env() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    return env


def test_cli_bad_prices_exits_2(tmp_path: Path):
    cfg = Path("tests/fixtures/regime_test_cfg.yaml")
    prices = Path("tests/fixtures/prices_missing_ticker.csv")
    out_path = tmp_path / "out.json"

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
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 2
    assert "Missing required tickers" in result.stderr


def test_cli_insufficient_history_exits_3(tmp_path: Path):
    cfg = Path("tests/fixtures/regime_test_cfg.yaml")
    prices = Path("tests/fixtures/prices_overlap_short.csv")
    out_path = tmp_path / "out.json"

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
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 3
    assert "Insufficient overlap" in result.stderr


def test_cli_no_clobber_fails(tmp_path: Path):
    cfg = Path("tests/fixtures/regime_test_cfg.yaml")
    prices = Path("tests/fixtures/prices_replay_long.csv")
    out_path = tmp_path / "replay.csv"
    out_path.write_text("already", encoding="utf-8")

    store_dir = tmp_path / "store"

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
        str(store_dir),
        "--start",
        "2026-01-16",
        "--end",
        "2026-01-20",
        "--out",
        str(out_path),
        "--no-clobber",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 2
    assert "Refusing to overwrite" in result.stderr