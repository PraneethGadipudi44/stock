from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from core.regime.config import load_regime_config, validate_regime_config
from core.regime.metrics_builder import build_metrics_from_prices
from core.regime.prices_io import read_prices_csv, rows_to_records
from core.regime.run_snapshot import run_snapshot


def test_snapshot_contract_from_prices():
    root = Path(__file__).resolve().parents[1]
    prices_path = root / "tests" / "fixtures" / "prices_small.csv"
    cfg_path = root / "tests" / "fixtures" / "regime_test_cfg.yaml"
    schema_path = root / "contracts" / "regime_snapshot.schema.json"

    cfg = validate_regime_config(load_regime_config(str(cfg_path)))
    rows = read_prices_csv(str(prices_path))
    metrics = build_metrics_from_prices(rows_to_records(rows), cfg)

    dates_by_ticker = {}
    for row in rows:
        dates_by_ticker.setdefault(row.ticker, []).append(row.date)
    as_of_date = min(max(dates) for dates in dates_by_ticker.values())

    meta = {
        "as_of_ts": f"{as_of_date.isoformat()}T00:00:00Z",
        "session": "close",
        "engine_version": "regime_v1",
        "universe": "US_EQ_ETF",
        "benchmarks": ["SPY", "QQQ", "IWM"],
        "reasoning": ["Contract check", "Prices fixture", "Deterministic"],
        "metrics_snapshot": {"recent_change_window_days": 20},
    }

    output = run_snapshot(metrics, meta, cfg_path=str(cfg_path))
    snapshot = json.loads(output)

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.validate(snapshot, schema)
