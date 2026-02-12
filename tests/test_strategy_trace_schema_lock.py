from __future__ import annotations

import json
from pathlib import Path


def test_strategy_trace_schema_lock():
    schema = json.loads(
        Path("contracts/regime_strategy_trace.schema.v1.json").read_text(
            encoding="utf-8"
        )
    )
    required = {
        "schema_version",
        "snapshot_id",
        "as_of_ts",
        "strategy_schema_version",
        "explain_schema_version",
        "strategy_config_hash",
        "regime_config_hash",
        "explain_config_hash",
        "inputs_hash",
    }
    assert set(schema["required"]) == required
    assert schema["properties"]["schema_version"]["const"] == 1
    assert schema["properties"]["strategy_schema_version"]["enum"] == [1, 2]
    assert schema["properties"]["explain_schema_version"]["const"] == 1
