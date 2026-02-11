from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from core.regime import engine
from core.regime.config import load_regime_config, validate_regime_config
from core.regime.metrics_builder import build_metrics_from_prices
from core.regime.prices_io import read_prices_csv, rows_to_records
from core.regime.run_snapshot import run_snapshot


def _latest_common_date(rows):
    dates_by_ticker = {}
    for row in rows:
        dates_by_ticker.setdefault(row.ticker, []).append(row.date)
    latest_dates = [max(dates) for dates in dates_by_ticker.values()]
    return min(latest_dates)


def test_golden_snapshot_from_prices(monkeypatch):
    fixed_uuid = UUID("00000000-0000-0000-0000-0000000000a1")
    monkeypatch.setattr(engine, "uuid4", lambda: fixed_uuid)

    root = Path(__file__).resolve().parents[1]
    prices_path = root / "tests" / "fixtures" / "prices_small.csv"
    cfg_path = root / "tests" / "fixtures" / "regime_test_cfg.yaml"

    cfg = validate_regime_config(load_regime_config(str(cfg_path)))
    rows = read_prices_csv(str(prices_path))
    metrics = build_metrics_from_prices(rows_to_records(rows), cfg)

    as_of_date = _latest_common_date(rows)
    meta = {
        "as_of_ts": f"{as_of_date.isoformat()}T00:00:00Z",
        "session": "close",
        "engine_version": "regime_v1",
        "universe": "US_EQ_ETF",
        "benchmarks": ["SPY", "QQQ", "IWM"],
        "reasoning": ["Prices fixture", "Metrics builder", "Deterministic"],
        "metrics_snapshot": {"recent_change_window_days": 20},
        "inputs_hash": "prices-fixture",
    }

    output = run_snapshot(metrics, meta, cfg_path=str(cfg_path))

    fixture_path = root / "tests" / "fixtures" / "regime_snapshot_prices_golden.json"
    expected = fixture_path.read_text(encoding="utf-8")

    assert output == expected
    json.loads(output)
