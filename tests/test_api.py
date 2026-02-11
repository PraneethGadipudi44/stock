from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from core.regime.api import create_app
from core.regime.prices_io import read_prices_csv


def test_api_snapshot_and_history(tmp_path: Path):
    app = create_app(store_dir=str(tmp_path))
    client = TestClient(app)

    root = Path(__file__).resolve().parents[1]
    prices_path = root / "tests" / "fixtures" / "prices_small.csv"
    cfg_path = root / "tests" / "fixtures" / "regime_test_cfg.yaml"

    rows = read_prices_csv(str(prices_path))
    records = [
        {"date": row.date.isoformat(), "ticker": row.ticker, "close": row.close}
        for row in rows
    ]
    body = {
        "prices": records,
        "cfg_path": str(cfg_path),
        "session": "close",
        "benchmarks": ["SPY", "QQQ", "IWM"],
        "reasoning": ["API test", "Prices fixture", "Deterministic"],
        "recent_change_window_days": 20,
    }

    response = client.post("/v1/snapshot", json=body)
    assert response.status_code == 200
    snapshot = response.json()
    assert snapshot["snapshot_id"]

    latest = client.get("/v1/latest")
    assert latest.status_code == 200
    latest_payload = latest.json()
    assert latest_payload["snapshot"]["snapshot_id"] == snapshot["snapshot_id"]

    history = client.get("/v1/history?limit=5")
    assert history.status_code == 200
    assert isinstance(history.json(), list)
