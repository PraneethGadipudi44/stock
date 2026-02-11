from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

from core.regime.config import load_regime_config


def _make_prices(days: int, tickers: list[str]) -> list[dict]:
    rows = []
    start = date(2026, 1, 1)
    base_map = {
        "SPY": 100.0,
        "TLT": 90.0,
        "HYG": 80.0,
        "LQD": 85.0,
        "VIX": 20.0,
    }
    trend_map = {
        "SPY": 0.2,
        "TLT": -0.05,
        "HYG": 0.1,
        "LQD": 0.05,
        "VIX": 0.02,
    }
    for idx in range(days):
        current = start + timedelta(days=idx)
        for ticker in tickers:
            close = base_map[ticker] + trend_map[ticker] * idx
            rows.append(
                {"date": current.isoformat(), "ticker": ticker, "close": close}
            )
    return rows


def _write_prices_csv(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("date,ticker,close\n")
        for row in rows:
            handle.write(f"{row['date']},{row['ticker']},{row['close']}\n")


def _write_small_cfg(path: Path) -> None:
    cfg = load_regime_config("config/regime_v1.yaml")
    metrics = dict(cfg["metrics"])
    metrics.update(
        {
            "sma_short_window": 5,
            "sma_long_window": 10,
            "slope_window": 3,
            "chop_window": 5,
            "vol_window": 5,
            "vol_lookback": 10,
            "vix_pct_lookback": 10,
            "rs_window": 5,
        }
    )
    cfg["metrics"] = metrics
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")


def test_cli_snapshot_and_replay(tmp_path: Path):
    cfg_path = tmp_path / "cfg.yaml"
    _write_small_cfg(cfg_path)

    csv_path = tmp_path / "prices.csv"
    rows = _make_prices(40, ["SPY", "TLT", "HYG", "LQD", "VIX"])
    _write_prices_csv(csv_path, rows)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")

    snapshot_out = tmp_path / "snapshot.json"
    snapshot_cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "snapshot",
        "--cfg",
        str(cfg_path),
        "--prices",
        str(csv_path),
        "--out",
        str(snapshot_out),
    ]
    subprocess.run(snapshot_cmd, capture_output=True, text=True, env=env, check=True)
    payload = json.loads(snapshot_out.read_text(encoding="utf-8"))
    assert payload["snapshot_id"]

    store_dir = tmp_path / "store"
    out_csv = tmp_path / "replay.csv"
    dates = sorted({row["date"] for row in rows})
    replay_cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "replay",
        "--cfg",
        str(cfg_path),
        "--prices",
        str(csv_path),
        "--store",
        str(store_dir),
        "--start",
        dates[20],
        "--end",
        dates[-1],
        "--out",
        str(out_csv),
    ]
    subprocess.run(replay_cmd, capture_output=True, text=True, env=env, check=True)

    assert out_csv.exists()
    assert (store_dir / "latest.json").exists()

    report_cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "report",
        "--snapshot",
        str(snapshot_out),
    ]
    report_result = subprocess.run(
        report_cmd, capture_output=True, text=True, env=env, check=True
    )
    assert "Market Phase" in report_result.stdout

    tune_out = tmp_path / "tune.csv"
    tune_cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "tune",
        "--cfg",
        str(cfg_path),
        "--out",
        str(tune_out),
    ]
    subprocess.run(tune_cmd, capture_output=True, text=True, env=env, check=True)
    assert tune_out.exists()
