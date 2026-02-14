from __future__ import annotations

import json
from pathlib import Path


def test_brief_strategy_meta_schema_lock():
    schema = json.loads(
        Path("contracts/regime_brief_strategy_meta.schema.v1.json").read_text(
            encoding="utf-8"
        )
    )
    required = {
        "schema_version",
        "adapter_version",
        "inputs",
        "inputs_hash",
        "normalized_strategy_hash",
        "markdown_hash",
        "rows",
        "cache_hit",
    }
    assert set(schema["required"]) == required
    assert schema["properties"]["schema_version"]["const"] == 1
    assert schema["properties"]["adapter_version"]["const"] == "brief_strategy_adapter_v1"
