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
