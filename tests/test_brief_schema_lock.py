from __future__ import annotations

import json
from pathlib import Path


def test_brief_schema_lock():
    schema = json.loads(
        Path("contracts/regime_brief.schema.v1.json").read_text(encoding="utf-8")
    )
    required = {
        "schema_version",
        "as_of",
        "focus_list",
        "today_catalysts",
        "recent_catalysts",
        "price_moves",
        "data_coverage",
    }
    assert set(schema["required"]) == required
    assert schema["properties"]["schema_version"]["const"] == 1
