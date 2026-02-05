from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from core.regime import engine
from core.regime.run_snapshot import run_snapshot


def test_golden_regime_snapshot(monkeypatch):
    fixed_uuid = UUID("00000000-0000-0000-0000-000000000001")
    monkeypatch.setattr(engine, "uuid4", lambda: fixed_uuid)

    metrics = {
        "basket_price_above_50dma_pct": 80.0,
        "basket_price_above_200dma_pct": 70.0,
        "basket_ma50_slope_20d": 2.0,
        "chop_score": 30.0,
        "realized_vol_20d_pct": 40.0,
        "vix_pct": 35.0,
        "hyg_lqd_rs_20d": 2.0,
        "spy_tlt_rs_20d": 1.5,
    }
    meta = {
        "as_of_ts": "2026-02-05T13:30:00Z",
        "session": "open",
        "engine_version": "regime_v1",
        "universe": "US_EQ_ETF",
        "benchmarks": ["SPY", "QQQ", "IWM"],
        "reasoning": ["Position strong", "Slope positive", "Risk on"],
        "metrics_snapshot": {
            "recent_change_window_days": 20,
        },
        "inputs_hash": "fixturehash",
    }

    cfg_path = str(ROOT / "config" / "regime_v1.yaml")
    output = run_snapshot(metrics, meta, cfg_path=cfg_path)

    fixture_path = ROOT / "tests" / "fixtures" / "regime_snapshot_golden.json"
    expected = fixture_path.read_text(encoding="utf-8")

    assert output == expected

    # Also ensure JSON parses for sanity
    json.loads(output)
