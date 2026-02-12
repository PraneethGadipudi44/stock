from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List


def _parse_as_of(value: str) -> datetime:
    text = value
    if text.endswith("Z"):
        text = text[:-1]
    return datetime.fromisoformat(text)


def _delta_float(curr: Dict[str, Any], prev: Dict[str, Any], key: str) -> float:
    if key not in curr or key not in prev:
        raise ValueError(f"Missing metrics_snapshot key: {key}")
    return float(curr[key]) - float(prev[key])


def _delta_int(curr: Dict[str, Any], prev: Dict[str, Any], key: str) -> int:
    if key not in curr or key not in prev:
        raise ValueError(f"Missing metrics_snapshot key: {key}")
    return int(curr[key]) - int(prev[key])


def _line_changed(label: str, prev: str, curr: str) -> str:
    if prev != curr:
        return f"{label}: {prev} -> {curr}"
    return f"{label}: unchanged ({curr})"


def build_diff(prev: Dict[str, Any], curr: Dict[str, Any]) -> Dict[str, Any]:
    prev_schema = prev.get("schema_version")
    curr_schema = curr.get("schema_version")
    if prev_schema != curr_schema:
        raise ValueError("Snapshot schema versions must match.")
    if prev_schema is None:
        raise ValueError("Missing snapshot schema_version.")

    prev_id = prev.get("snapshot_id")
    curr_id = curr.get("snapshot_id")
    if prev_id == curr_id:
        raise ValueError("Snapshot IDs must differ.")

    prev_ts = prev.get("as_of_ts")
    curr_ts = curr.get("as_of_ts")
    if not prev_ts or not curr_ts:
        raise ValueError("Missing as_of_ts.")
    if _parse_as_of(prev_ts) >= _parse_as_of(curr_ts):
        raise ValueError("as_of_ts ordering must be prev < curr.")

    market_phase_changed = prev.get("market_phase") != curr.get("market_phase")
    trend_regime_changed = prev.get("trend_regime") != curr.get("trend_regime")
    vol_regime_changed = prev.get("vol_regime") != curr.get("vol_regime")
    risk_tone_changed = prev.get("risk_tone") != curr.get("risk_tone")

    confidence_delta = round(
        float(curr.get("confidence", 0.0)) - float(prev.get("confidence", 0.0)),
        4,
    )

    prev_drivers = set(prev.get("change_drivers", []) or [])
    curr_drivers = set(curr.get("change_drivers", []) or [])
    change_drivers_added = sorted(curr_drivers - prev_drivers)
    change_drivers_removed = sorted(prev_drivers - curr_drivers)

    prev_metrics = prev.get("metrics_snapshot", {})
    curr_metrics = curr.get("metrics_snapshot", {})

    metrics_delta = {
        "vote_disagreement_score_delta": round(
            _delta_float(curr_metrics, prev_metrics, "vote_disagreement_score"),
            4,
        ),
        "recent_change_window_days_delta": _delta_int(
            curr_metrics, prev_metrics, "recent_change_window_days"
        ),
    }

    diff_summary: List[str] = [
        _line_changed("market_phase", prev.get("market_phase"), curr.get("market_phase")),
        f"confidence: {confidence_delta:+.4f}",
        _line_changed("trend_regime", prev.get("trend_regime"), curr.get("trend_regime")),
        _line_changed("vol_regime", prev.get("vol_regime"), curr.get("vol_regime")),
        _line_changed("risk_tone", prev.get("risk_tone"), curr.get("risk_tone")),
    ]

    return {
        "schema_version": 1,
        "snapshot_id_prev": prev_id,
        "snapshot_id_curr": curr_id,
        "as_of_prev": prev_ts,
        "as_of_curr": curr_ts,
        "snapshot_schema_version": prev_schema,
        "market_phase_changed": market_phase_changed,
        "trend_regime_changed": trend_regime_changed,
        "vol_regime_changed": vol_regime_changed,
        "risk_tone_changed": risk_tone_changed,
        "confidence_delta": confidence_delta,
        "change_drivers_added": change_drivers_added,
        "change_drivers_removed": change_drivers_removed,
        "metrics_delta": metrics_delta,
        "diff_summary": diff_summary,
    }


def diff_json(prev: Dict[str, Any], curr: Dict[str, Any]) -> str:
    payload = build_diff(prev, curr)
    return json.dumps(payload, indent=2, sort_keys=True)
