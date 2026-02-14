from __future__ import annotations

import json
from pathlib import Path


def test_catalyst_record_schema_lock():
    schema = json.loads(
        Path("contracts/regime_catalyst_record.schema.v1.json").read_text(
            encoding="utf-8"
        )
    )
    required = {
        "schema_version",
        "ticker",
        "event_date",
        "event_type",
        "form",
        "filing_date",
        "acceptance_datetime",
        "accession_number",
        "url_filing_detail",
        "has_price_row",
    }
    assert set(schema["required"]) == required
    assert schema["properties"]["schema_version"]["const"] == 1
    assert schema["properties"]["event_type"]["const"] == "sec_filing"
