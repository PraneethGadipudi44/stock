from __future__ import annotations

from pathlib import Path

from core.regime.resources import read_text


def test_packaged_resources_match_repo_files():
    root = Path(__file__).resolve().parents[1]
    mapping = {
        "regime_v1.yaml": root / "config" / "regime_v1.yaml",
        "strategy_v1.yaml": root / "config" / "strategy_v1.yaml",
        "regime_snapshot.schema.json": root / "contracts" / "regime_snapshot.schema.json",
        "regime_metrics_input.schema.v1.json": root / "contracts" / "regime_metrics_input.schema.v1.json",
        "regime_store_entry.schema.v1.json": root / "contracts" / "regime_store_entry.schema.v1.json",
        "regime_explain.schema.v1.json": root / "contracts" / "regime_explain.schema.v1.json",
        "regime_strategy.schema.v1.json": root / "contracts" / "regime_strategy.schema.v1.json",
        "regime_strategy.schema.v2.json": root / "contracts" / "regime_strategy.schema.v2.json",
        "regime_strategy_trace.schema.v1.json": root / "contracts" / "regime_strategy_trace.schema.v1.json",
    }

    for name, path in mapping.items():
        assert path.exists(), f"Missing repo file: {path}"
        assert read_text(name) == path.read_text(encoding="utf-8")
