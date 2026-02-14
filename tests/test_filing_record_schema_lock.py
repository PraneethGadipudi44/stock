from __future__ import annotations

import json
from pathlib import Path


def test_filing_record_schema_lock():
    schema = json.loads(
        Path("contracts/regime_filing_record.schema.v1.json").read_text(
            encoding="utf-8"
        )
    )
    required = {
        "acceptance_datetime",
        "accession_number",
        "cik",
        "filing_date",
        "form",
        "primary_doc",
        "ticker",
        "url_filing_detail",
    }
    assert set(schema["required"]) == required
    assert schema["properties"]["form"]["enum"] == ["10-K", "10-Q", "8-K"]
    assert schema["properties"]["cik"]["pattern"] == "^\\d{10}$"
    assert schema["properties"]["url_filing_detail"]["pattern"].startswith(
        "^https://www\\.sec\\.gov/Archives/edgar/data/"
    )
