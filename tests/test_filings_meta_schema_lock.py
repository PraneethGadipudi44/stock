from __future__ import annotations

import json
from pathlib import Path


def test_filings_meta_schema_lock():
    schema = json.loads(
        Path("contracts/regime_filings_meta.schema.v1.json").read_text(
            encoding="utf-8"
        )
    )
    required = {
        "schema_version",
        "provider",
        "provider_version",
        "adapter_version",
        "ticker",
        "cik",
        "start",
        "end",
        "forms",
        "request_canonical",
        "cache_key",
        "rows",
        "source_hash",
        "normalized_jsonl_hash",
        "cache_hit",
    }
    assert set(schema["required"]) == required
    assert schema["properties"]["schema_version"]["const"] == 1
    assert schema["properties"]["provider"]["const"] == "edgar"
    assert (
        schema["properties"]["provider_version"]["const"]
        == "submissions+archives_v1"
    )
    assert schema["properties"]["adapter_version"]["const"] == "filings_adapter_v1"
