from __future__ import annotations

import json
from pathlib import Path


def test_audit_manifest_meta_schema_lock():
    schema = json.loads(
        Path("contracts/regime_audit_manifest_meta.schema.v1.json").read_text(
            encoding="utf-8"
        )
    )
    required = {
        "schema_version",
        "adapter_version",
        "inputs",
        "inputs_hash",
        "normalized_manifest_hash",
        "rows",
        "cache_hit",
    }
    assert set(schema["required"]) == required
    assert schema["properties"]["schema_version"]["const"] == 1
    assert (
        schema["properties"]["adapter_version"]["const"]
        == "audit_manifest_adapter_v1"
    )
