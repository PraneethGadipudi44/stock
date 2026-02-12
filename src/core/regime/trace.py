from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def _normalize_optional_path(value: Optional[str]) -> Optional[str]:
    if not value or value == "-":
        return None
    return Path(value).name.replace("\\", "/")


def build_trace(
    strategy_payload: Dict[str, Any],
    explain_payload: Dict[str, Any],
    *,
    strategy_file: Optional[str] = None,
    explain_file: Optional[str] = None,
) -> Dict[str, Any]:
    strategy_snapshot_id = strategy_payload.get("snapshot_id")
    explain_snapshot_id = explain_payload.get("snapshot_id")
    if strategy_snapshot_id != explain_snapshot_id:
        raise ValueError("Snapshot ID mismatch between strategy and explain.")

    strategy_as_of = strategy_payload.get("as_of_ts")
    explain_as_of = explain_payload.get("as_of_ts")
    if strategy_as_of != explain_as_of:
        raise ValueError("as_of_ts mismatch between strategy and explain.")

    strategy_schema_version = int(strategy_payload.get("schema_version", 0))
    if strategy_schema_version not in {1, 2}:
        raise ValueError("Unsupported strategy schema version.")

    explain_schema_version = int(explain_payload.get("schema_version", 0))
    if explain_schema_version != 1:
        raise ValueError("Unsupported explain schema version.")

    strategy_snapshot_schema = strategy_payload.get("snapshot_schema_version")
    explain_snapshot_schema = explain_payload.get("snapshot_schema_version")
    if (
        strategy_snapshot_schema is not None
        and explain_snapshot_schema is not None
        and strategy_snapshot_schema != explain_snapshot_schema
    ):
        raise ValueError(
            "Snapshot schema version mismatch between strategy and explain."
        )

    strategy_config_hash = strategy_payload.get("strategy_config_hash")
    if not strategy_config_hash:
        raise ValueError("strategy_config_hash is required.")

    regime_config_hash = strategy_payload.get("regime_config_hash")
    if strategy_schema_version == 1 and regime_config_hash is not None:
        raise ValueError("regime_config_hash must be null for strategy schema v1.")

    explain_config_hash = explain_payload.get("config_hash")
    if not explain_config_hash:
        raise ValueError("explain config_hash is required.")

    strategy_inputs_hash = strategy_payload.get("inputs_hash")
    explain_inputs_hash = explain_payload.get("inputs_hash")
    if (
        strategy_inputs_hash is not None
        and explain_inputs_hash is not None
        and strategy_inputs_hash != explain_inputs_hash
    ):
        raise ValueError("inputs_hash mismatch between strategy and explain.")

    inputs_hash = (
        strategy_inputs_hash
        if strategy_inputs_hash is not None
        else explain_inputs_hash
    )

    trace_payload: Dict[str, Any] = {
        "schema_version": 1,
        "snapshot_id": strategy_snapshot_id,
        "as_of_ts": strategy_as_of,
        "strategy_schema_version": strategy_schema_version,
        "explain_schema_version": explain_schema_version,
        "strategy_config_hash": strategy_config_hash,
        "regime_config_hash": regime_config_hash,
        "explain_config_hash": explain_config_hash,
        "inputs_hash": inputs_hash,
    }

    engine_version = explain_payload.get("engine_version")
    if engine_version is not None:
        trace_payload["engine_version"] = engine_version

    normalized_strategy = _normalize_optional_path(strategy_file)
    if normalized_strategy is not None:
        trace_payload["strategy_file"] = normalized_strategy

    normalized_explain = _normalize_optional_path(explain_file)
    if normalized_explain is not None:
        trace_payload["explain_file"] = normalized_explain

    return trace_payload


def trace_json(
    strategy_payload: Dict[str, Any],
    explain_payload: Dict[str, Any],
    *,
    strategy_file: Optional[str] = None,
    explain_file: Optional[str] = None,
) -> str:
    payload = build_trace(
        strategy_payload,
        explain_payload,
        strategy_file=strategy_file,
        explain_file=explain_file,
    )
    return json.dumps(payload, indent=2, sort_keys=True)
