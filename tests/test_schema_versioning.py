from __future__ import annotations

import json
from pathlib import Path


EXPECTED_SCHEMA_VERSION = 1

EXPECTED_REQUIRED_BY_VERSION = {
    1: {
        "snapshot_id",
        "schema_version",
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
}


def test_schema_version_const_and_required_lock():
    root = Path(__file__).resolve().parents[1]
    schema_path = root / "contracts" / "regime_snapshot.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    props = schema["properties"]
    schema_version = props["schema_version"]
    if "const" in schema_version:
        assert schema_version["const"] == EXPECTED_SCHEMA_VERSION
    elif "enum" in schema_version:
        assert schema_version["enum"] == [EXPECTED_SCHEMA_VERSION]
    else:
        raise AssertionError("schema_version must define const or enum.")

    expected_required = EXPECTED_REQUIRED_BY_VERSION[EXPECTED_SCHEMA_VERSION]
    assert set(schema["required"]) == expected_required
