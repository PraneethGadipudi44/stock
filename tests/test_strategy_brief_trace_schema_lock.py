from __future__ import annotations

import json
from pathlib import Path


def test_strategy_brief_trace_schema_lock():
    schema = json.loads(
        Path("contracts/regime_strategy_brief_trace.schema.v1.json").read_text(
            encoding="utf-8"
        )
    )
    required = {"schema_version", "as_of", "inputs_hash", "artifacts", "coverage"}
    assert set(schema["required"]) == required
    assert schema["properties"]["schema_version"]["const"] == 1
