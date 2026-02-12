from __future__ import annotations

import json
from pathlib import Path


def test_strategy_schema_lock_v1():
    schema = json.loads(
        Path("contracts/regime_strategy.schema.v1.json").read_text(encoding="utf-8")
    )
    required = {
        "schema_version",
        "strategy_version",
        "strategy_config_source",
        "strategy_config_hash",
        "config_hash",
        "as_of_ts",
        "snapshot_id",
        "market_phase",
        "trend_regime",
        "vol_regime",
        "risk_tone",
        "confidence",
        "action_recommendation",
        "playbook",
        "guardrails",
        "rules_fired",
        "rationale",
        "strategy_inputs",
    }
    assert set(schema["required"]) == required
    assert schema["properties"]["schema_version"]["const"] == 1
    assert "none" in schema["properties"]["playbook"]["enum"]
    assert "do_nothing" in schema["properties"]["action_recommendation"]["enum"]
    strategy_inputs = schema["properties"]["strategy_inputs"]
    assert strategy_inputs["additionalProperties"] is False


def test_strategy_schema_lock_v2():
    schema = json.loads(
        Path("contracts/regime_strategy.schema.v2.json").read_text(encoding="utf-8")
    )
    required = {
        "schema_version",
        "strategy_version",
        "strategy_config_source",
        "strategy_config_hash",
        "regime_config_hash",
        "as_of_ts",
        "snapshot_id",
        "snapshot_schema_version",
        "market_phase",
        "trend_regime",
        "vol_regime",
        "risk_tone",
        "confidence",
        "action_recommendation",
        "playbook",
        "guardrails",
        "rules_fired",
        "rationale",
        "strategy_inputs",
    }
    assert set(schema["required"]) == required
    assert schema["properties"]["schema_version"]["const"] == 2
    assert schema["properties"]["market_phase"]["type"] == "string"
