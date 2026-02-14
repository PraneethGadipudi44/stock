from __future__ import annotations

import json
from pathlib import Path


def test_prices_meta_schema_lock():
    schema = json.loads(
        Path("contracts/regime_prices_meta.schema.v1.json").read_text(
            encoding="utf-8"
        )
    )
    required = {
        "schema_version",
        "provider",
        "provider_version",
        "adapter_version",
        "endpoint",
        "request_canonical",
        "cache_key",
        "symbol",
        "start",
        "end",
        "date_semantics",
        "rounding_mode",
        "rows",
        "source_hash",
        "normalized_csv_hash",
        "cache_hit",
    }
    assert set(schema["required"]) == required
    assert schema["properties"]["schema_version"]["const"] == 1
