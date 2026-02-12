from __future__ import annotations

import json
from pathlib import Path


def test_diff_schema_lock():
    schema = json.loads(
        Path("contracts/regime_diff.schema.v1.json").read_text(encoding="utf-8")
    )
    required = {
        "schema_version",
        "snapshot_id_prev",
        "snapshot_id_curr",
        "as_of_prev",
        "as_of_curr",
        "snapshot_schema_version",
        "market_phase_changed",
        "trend_regime_changed",
        "vol_regime_changed",
        "risk_tone_changed",
        "confidence_delta",
        "change_drivers_added",
        "change_drivers_removed",
        "metrics_delta",
        "diff_summary",
    }
    assert set(schema["required"]) == required
    assert schema["properties"]["schema_version"]["const"] == 1
    metrics = schema["properties"]["metrics_delta"]
    assert metrics["additionalProperties"] is False
