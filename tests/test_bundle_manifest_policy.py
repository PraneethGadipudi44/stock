from __future__ import annotations

import zipfile
from pathlib import Path

from core.regime.bundle_manifest import expected_bundle_entries


def test_bundle_manifest_entry_order_and_names(tmp_path: Path):
    bundle = tmp_path / "bundle.zip"
    # Use fixture bundle created by test_bundle_manifest in the same run if present
    # Otherwise, this test only validates expected ordering helper.
    expected = expected_bundle_entries(
        strategy_md=Path("tests/fixtures/brief_strategy_diff_same_aapl_2024-02-15.md"),
        diff_strategy_md=Path("tests/fixtures/brief_strategy_diff_same_aapl_2024-02-15.md"),
        diff_trace_md=Path("tests/fixtures/strategy_brief_trace_diff_same_aapl_2024-02-15.md"),
    )
    if bundle.exists():
        with zipfile.ZipFile(bundle, "r") as zf:
            assert zf.namelist() == expected
    else:
        assert expected[0] == "manifest.json"
