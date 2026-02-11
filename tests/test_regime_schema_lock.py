from __future__ import annotations

import json
from pathlib import Path


def test_regime_snapshot_schema_lock():
    root = Path(__file__).resolve().parents[1]
    schema_path = root / "contracts" / "regime_snapshot.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    expected_required = {
        "snapshot_id",
        "as_of_ts",
        "session",
        "engine_version",
        "universe",
        "benchmarks",
        "market_phase",
        "trend_regime",
        "vol_regime",
        "risk_tone",
        "confidence",
        "reasoning",
        "signal_votes",
        "metrics_snapshot",
        "regime_changed",
        "change_reason",
        "change_drivers",
    }
    assert set(schema["required"]) == expected_required

    props = schema["properties"]
    assert props["snapshot_id"]["minLength"] == 8
    assert props["reasoning"]["minItems"] == 3
    assert props["reasoning"]["maxItems"] == 5
    assert props["reasoning"]["items"]["minLength"] == 3
    assert props["reasoning"]["items"]["maxLength"] == 200
    assert props["change_reason"]["minLength"] == 3
    assert props["change_reason"]["maxLength"] == 240
    assert props["benchmarks"]["uniqueItems"] is True
    assert props["confidence"]["minimum"] == 0
    assert props["confidence"]["maximum"] == 100

    metrics_snapshot = schema["$defs"]["MetricsSnapshot"]
    assert metrics_snapshot["additionalProperties"] is True


def test_regime_store_entry_schema_lock():
    root = Path(__file__).resolve().parents[1]
    schema_path = root / "contracts" / "regime_store_entry.schema.v1.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert set(schema["required"]) == {"snapshot", "metadata"}
    metadata = schema["properties"]["metadata"]
    assert set(metadata["required"]) == {"stored_at", "inputs_hash"}


def test_regime_metrics_input_schema_lock():
    root = Path(__file__).resolve().parents[1]
    schema_path = root / "contracts" / "regime_metrics_input.schema.v1.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    required = {
        "basket_price_above_50dma_pct",
        "basket_price_above_200dma_pct",
        "basket_ma50_slope_20d",
        "chop_score",
        "realized_vol_20d_pct",
        "vix_pct",
        "hyg_lqd_rs_20d",
        "spy_tlt_rs_20d",
    }
    assert set(schema["required"]) == required
    assert schema["additionalProperties"] is False
