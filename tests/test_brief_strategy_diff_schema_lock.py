from __future__ import annotations

import json
from pathlib import Path


def test_brief_strategy_diff_schema_lock():
    schema = json.loads(
        Path("contracts/regime_brief_strategy_diff.schema.v1.json").read_text(
            encoding="utf-8"
        )
    )
    required = {
        "schema_version",
        "left",
        "right",
        "inputs_hash",
        "changes",
        "coverage_delta",
        "summary",
    }
    assert set(schema["required"]) == required
    assert schema["properties"]["schema_version"]["const"] == 1
