from __future__ import annotations

import json
from pathlib import Path

from core.regime.strategy import build_strategy, load_strategy_config, strategy_config_hash


def test_transition_guardrail_do_nothing():
    snapshot = json.loads(
        Path("tests/fixtures/regime_snapshot_prices_golden.json").read_text(
            encoding="utf-8"
        )
    )
    cfg = load_strategy_config("config/strategy_v1.yaml")
    cfg_hash = strategy_config_hash("config/strategy_v1.yaml")
    output = build_strategy(snapshot, cfg, "config/strategy_v1.yaml", cfg_hash)
    assert output["action_recommendation"] == "do_nothing"
    assert output["playbook"] == "none"


def test_low_confidence_observe_only():
    snapshot = json.loads(
        Path("tests/fixtures/regime_snapshot_golden.json").read_text(
            encoding="utf-8"
        )
    )
    snapshot["market_phase"] = "trend_up"
    snapshot["confidence"] = 10.0
    cfg = load_strategy_config("config/strategy_v1.yaml")
    cfg_hash = strategy_config_hash("config/strategy_v1.yaml")
    output = build_strategy(snapshot, cfg, "config/strategy_v1.yaml", cfg_hash)
    assert output["action_recommendation"] == "observe_only"
    assert output["playbook"] == "none"
