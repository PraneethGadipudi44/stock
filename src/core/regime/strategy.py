from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .resources import read_text


ALLOWED_ACTIONS = {"do_nothing", "observe_only", "risk_on", "reduce_risk"}
ALLOWED_PLAYBOOKS = {
    "none",
    "trend_follow",
    "mean_revert",
    "capital_preservation",
    "tactical_breakout",
}


def load_strategy_config(path: Optional[str] = None) -> Dict[str, Any]:
    if path:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    else:
        data = yaml.safe_load(read_text("strategy_v1.yaml"))
    if data is None:
        raise ValueError("Strategy config is empty or invalid YAML.")
    return data


def validate_strategy_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    for key in ("version", "thresholds", "actions", "playbooks"):
        if key not in cfg:
            raise KeyError(f"Missing strategy config key: {key}")

    thresholds = cfg["thresholds"]
    for key in ("min_confidence", "trend_confidence", "range_confidence"):
        if key not in thresholds:
            raise KeyError(f"Missing strategy config key: thresholds.{key}")

    actions = cfg["actions"]
    for key in ("transition", "low_confidence", "risk_on", "reduce_risk", "fallback"):
        if key not in actions:
            raise KeyError(f"Missing strategy config key: actions.{key}")
        if actions[key] not in ALLOWED_ACTIONS:
            raise ValueError(f"Invalid action: {actions[key]}")

    playbooks = cfg["playbooks"]
    for key in ("none", "capital_preservation", "trend_follow", "mean_revert"):
        if key not in playbooks:
            raise KeyError(f"Missing strategy config key: playbooks.{key}")
        if playbooks[key] not in ALLOWED_PLAYBOOKS:
            raise ValueError(f"Invalid playbook: {playbooks[key]}")

    return cfg


def strategy_config_hash(path: Optional[str]) -> str:
    if path:
        data = Path(path).read_bytes()
    else:
        data = read_text("strategy_v1.yaml").encode("utf-8")
    return sha256(data).hexdigest()


def _normalize_source(value: str) -> str:
    return value.replace("\\", "/")


def build_strategy(
    snapshot: Dict[str, Any],
    cfg: Dict[str, Any],
    cfg_source: str,
    cfg_hash: str,
) -> Dict[str, Any]:
    cfg = validate_strategy_config(cfg)

    thresholds = cfg["thresholds"]
    actions = cfg["actions"]
    playbooks = cfg["playbooks"]

    market_phase = snapshot["market_phase"]
    trend_regime = snapshot["trend_regime"]
    vol_regime = snapshot["vol_regime"]
    risk_tone = snapshot["risk_tone"]
    confidence = float(snapshot["confidence"])
    metrics_snapshot = snapshot["metrics_snapshot"]

    rules: set[str] = set()
    guardrails: set[str] = set()

    action = actions["fallback"]
    playbook = playbooks["none"]

    if market_phase == "transition":
        action = actions["transition"]
        playbook = playbooks["none"]
        rules.add("gate.transition_do_nothing")
        guardrails.add("guardrail.no_action_in_transition")
    elif confidence < float(thresholds["min_confidence"]):
        action = actions["low_confidence"]
        playbook = playbooks["none"]
        rules.add("gate.min_confidence_observe_only")
        guardrails.add("guardrail.min_confidence")
    elif vol_regime == "high":
        action = actions["reduce_risk"]
        playbook = playbooks["capital_preservation"]
        rules.add("playbook.capital_preservation")
        guardrails.add("guardrail.vol_high")
    elif trend_regime in ("trend_up", "trend_down") and confidence >= float(
        thresholds["trend_confidence"]
    ):
        action = actions["risk_on"]
        playbook = playbooks["trend_follow"]
        rules.add("playbook.trend_follow")
    elif trend_regime == "range" and confidence >= float(
        thresholds["range_confidence"]
    ):
        action = actions["risk_on"]
        playbook = playbooks["mean_revert"]
        rules.add("playbook.mean_revert")
    else:
        action = actions["fallback"]
        playbook = playbooks["none"]
        rules.add("gate.fallback_observe_only")

    rules_fired = sorted(rules)
    guardrails_list = sorted(guardrails)

    rationale = [
        f"market_phase={market_phase}",
        f"confidence={confidence:.2f}",
        f"trend_regime={trend_regime}, vol_regime={vol_regime}, risk_tone={risk_tone}",
    ]
    if action == "do_nothing":
        rationale.append("transition gate -> do_nothing")
    elif action == "observe_only":
        rationale.append("confidence below thresholds -> observe_only")
    elif action == "reduce_risk":
        rationale.append("vol_high -> capital_preservation")
    elif playbook == "trend_follow":
        rationale.append("trend regime with confidence >= threshold")
    elif playbook == "mean_revert":
        rationale.append("range regime with confidence >= threshold")

    if len(rationale) > 5:
        rationale = rationale[:5]
    while len(rationale) < 3:
        rationale.append("deterministic_rules")

    strategy_inputs = {
        "trend_regime": trend_regime,
        "vol_regime": vol_regime,
        "risk_tone": risk_tone,
        "market_phase": market_phase,
        "confidence": confidence,
        "recent_change_window_days": metrics_snapshot["recent_change_window_days"],
        "vote_disagreement_score": metrics_snapshot["vote_disagreement_score"],
    }

    return {
        "schema_version": 1,
        "strategy_version": cfg["version"],
        "strategy_config_source": _normalize_source(cfg_source),
        "strategy_config_hash": cfg_hash,
        "config_hash": cfg_hash,
        "as_of_ts": snapshot["as_of_ts"],
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot_schema_version": snapshot.get("schema_version"),
        "inputs_hash": snapshot.get("inputs_hash"),
        "market_phase": market_phase,
        "trend_regime": trend_regime,
        "vol_regime": vol_regime,
        "risk_tone": risk_tone,
        "confidence": confidence,
        "action_recommendation": action,
        "playbook": playbook,
        "guardrails": guardrails_list,
        "rules_fired": rules_fired,
        "rationale": rationale,
        "strategy_inputs": strategy_inputs,
    }


def strategy_json(
    snapshot: Dict[str, Any],
    cfg: Dict[str, Any],
    cfg_source: str,
    cfg_hash: str,
) -> str:
    payload = build_strategy(snapshot, cfg, cfg_source, cfg_hash)
    return json.dumps(payload, indent=2, sort_keys=True)
