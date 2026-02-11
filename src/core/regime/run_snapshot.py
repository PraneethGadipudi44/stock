from __future__ import annotations

import json
from typing import Any, Dict, Optional

from .config import load_regime_config, validate_regime_config
from .constants import RESERVED_METRICS_KEYS
from .engine import build_regime_snapshot
from .models import RegimeSnapshot, format_as_of_ts


def _metrics_extra_for_payload(extra: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in extra.items() if key not in RESERVED_METRICS_KEYS}


def _snapshot_to_dict(snapshot: RegimeSnapshot) -> Dict[str, Any]:
    extra = _metrics_extra_for_payload(snapshot.metrics_snapshot.extra)
    payload = {
        "snapshot_id": snapshot.snapshot_id,
        "schema_version": 1,
        "as_of_ts": format_as_of_ts(snapshot.as_of_ts),
        "session": snapshot.session,
        "engine_version": snapshot.engine_version,
        "universe": snapshot.universe,
        "benchmarks": snapshot.benchmarks,
        "market_phase": snapshot.market_phase,
        "trend_regime": snapshot.trend_regime,
        "vol_regime": snapshot.vol_regime,
        "risk_tone": snapshot.risk_tone,
        "confidence": snapshot.confidence,
        "reasoning": snapshot.reasoning,
        "signal_votes": {
            "trend": {
                "vote": snapshot.signal_votes.trend.vote,
                "score": snapshot.signal_votes.trend.score,
                "threshold": snapshot.signal_votes.trend.threshold,
                "passed": snapshot.signal_votes.trend.passed,
            },
            "vol": {
                "vote": snapshot.signal_votes.vol.vote,
                "score": snapshot.signal_votes.vol.score,
                "threshold": snapshot.signal_votes.vol.threshold,
                "passed": snapshot.signal_votes.vol.passed,
            },
            "risk": {
                "vote": snapshot.signal_votes.risk.vote,
                "score": snapshot.signal_votes.risk.score,
                "threshold": snapshot.signal_votes.risk.threshold,
                "passed": snapshot.signal_votes.risk.passed,
            },
        },
        "metrics_snapshot": {
            "vote_disagreement_score": snapshot.metrics_snapshot.vote_disagreement_score,
            "recent_change_window_days": snapshot.metrics_snapshot.recent_change_window_days,
            **extra,
        },
        "regime_changed": snapshot.regime_changed,
        "change_reason": snapshot.change_reason,
        "change_drivers": snapshot.change_drivers,
        "prev_snapshot_ref": snapshot.prev_snapshot_ref,
    }

    if snapshot.inputs_hash is not None:
        payload["inputs_hash"] = snapshot.inputs_hash

    return payload


def run_snapshot(
    metrics: Dict[str, Any],
    meta: Dict[str, Any],
    cfg_path: Optional[str] = None,
    previous: Optional[RegimeSnapshot] = None,
) -> str:
    """Build a regime snapshot and return JSON for persistence or transport."""
    cfg = validate_regime_config(load_regime_config(cfg_path))
    snapshot = build_regime_snapshot(metrics, meta, cfg, previous=previous)
    payload = _snapshot_to_dict(snapshot)
    return json.dumps(payload, indent=2, sort_keys=True)
