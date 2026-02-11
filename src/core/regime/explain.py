from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Optional

from .resources import read_text


def _hash_config(cfg_path: Optional[str]) -> str:
    if cfg_path:
        data = Path(cfg_path).read_bytes()
    else:
        data = read_text("regime_v1.yaml").encode("utf-8")
    return sha256(data).hexdigest()


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value


def _risk_strength(vote: str, score: float, cfg: Dict[str, Any]) -> float:
    risk_cfg = cfg["thresholds"]["risk"]
    pos_thr = min(risk_cfg["hyg_lqd_rs_20d_pos"], risk_cfg["spy_tlt_rs_20d_pos"])
    neg_thr = min(
        abs(risk_cfg["hyg_lqd_rs_20d_neg"]),
        abs(risk_cfg["spy_tlt_rs_20d_neg"]),
    )
    denom = neg_thr if vote == "risk_off" else pos_thr
    if not denom:
        return 0.0
    return _clamp(abs(score) / denom)


def _as_of_date(as_of_ts: str) -> str:
    if "T" in as_of_ts:
        return as_of_ts.split("T")[0]
    return datetime.fromisoformat(as_of_ts).date().isoformat()


def _normalize_source(value: str) -> str:
    return value.replace("\\", "/")


def _confidence_breakdown(
    snapshot: Dict[str, Any], cfg: Dict[str, Any]
) -> Dict[str, Any]:
    votes = snapshot["signal_votes"]
    metrics_snapshot = snapshot["metrics_snapshot"]

    weights = cfg["confidence"]["vote_weights"]
    penalties = cfg["confidence"]["penalties"]
    bounds = cfg["confidence"]["bounds"]
    transition_cfg = cfg["thresholds"]["transition"]

    max_conf = bounds["max"]
    min_conf = bounds["min"]

    trend_score = float(votes["trend"]["score"])
    vol_score = float(votes["vol"]["score"])
    risk_score = float(votes["risk"]["score"])

    trend_strength = _clamp(abs(trend_score) / 100.0)
    vol_strength = _clamp(abs(vol_score) / 100.0)
    risk_strength = _risk_strength(votes["risk"]["vote"], risk_score, cfg)

    weight_sum = float(sum(weights.values()) or 1.0)
    base = max_conf * (
        weights["trend"] * trend_strength
        + weights["vol"] * vol_strength
        + weights["risk"] * risk_strength
    ) / weight_sum

    score = float(base)
    penalties_applied = {
        "vol_high": 0.0,
        "risk_off": 0.0,
        "transition": 0.0,
        "disagreement": 0.0,
        "recent_change": 0.0,
    }

    if votes["vol"]["vote"] == "high":
        penalties_applied["vol_high"] = float(penalties["vol_high"])
        score -= penalties_applied["vol_high"]
    if votes["risk"]["vote"] == "risk_off":
        penalties_applied["risk_off"] = float(penalties["risk_off"])
        score -= penalties_applied["risk_off"]

    if metrics_snapshot["vote_disagreement_score"] >= transition_cfg[
        "vote_disagreement_score_cutoff"
    ]:
        penalties_applied["transition"] = float(penalties["transition"])
        score -= penalties_applied["transition"]

    penalties_applied["disagreement"] = float(
        penalties["disagreement_per_point"]
        * metrics_snapshot["vote_disagreement_score"]
    )
    score -= penalties_applied["disagreement"]

    if (
        metrics_snapshot["recent_change_window_days"]
        <= transition_cfg["recent_change_window_days_cutoff"]
    ):
        penalties_applied["recent_change"] = float(penalties["recent_change"])
        score -= penalties_applied["recent_change"]

    clamped = max(min_conf, min(max_conf, score))

    return {
        "value": snapshot["confidence"],
        "base": float(base),
        "raw_score": float(score),
        "clamped_score": float(clamped),
        "bounds": {"min": float(min_conf), "max": float(max_conf)},
        "weights": {
            "trend": float(weights["trend"]),
            "vol": float(weights["vol"]),
            "risk": float(weights["risk"]),
        },
        "strengths": {
            "trend": float(trend_strength),
            "vol": float(vol_strength),
            "risk": float(risk_strength),
        },
        "penalties": penalties_applied,
        "vote_disagreement_score": float(metrics_snapshot["vote_disagreement_score"]),
        "recent_change_window_days": int(
            metrics_snapshot["recent_change_window_days"]
        ),
    }


def build_explain_payload(
    snapshot: Dict[str, Any],
    metrics: Dict[str, Any],
    cfg: Dict[str, Any],
    cfg_source: str,
    cfg_path: Optional[str],
) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "snapshot_id": snapshot.get("snapshot_id"),
        "snapshot_schema_version": snapshot.get("schema_version"),
        "as_of_ts": snapshot.get("as_of_ts"),
        "as_of_date": _as_of_date(snapshot.get("as_of_ts", "")),
        "session": snapshot.get("session"),
        "engine_version": snapshot.get("engine_version"),
        "config_source": _normalize_source(cfg_source),
        "config_hash": _hash_config(cfg_path),
        "inputs_hash": snapshot.get("inputs_hash"),
        "benchmarks": snapshot.get("benchmarks", []),
        "metrics": metrics,
        "metrics_snapshot": snapshot.get("metrics_snapshot", {}),
        "signal_votes": snapshot.get("signal_votes", {}),
        "market_phase": snapshot.get("market_phase"),
        "trend_regime": snapshot.get("trend_regime"),
        "vol_regime": snapshot.get("vol_regime"),
        "risk_tone": snapshot.get("risk_tone"),
        "confidence_breakdown": _confidence_breakdown(snapshot, cfg),
        "regime_changed": snapshot.get("regime_changed"),
        "change_reason": snapshot.get("change_reason"),
        "change_drivers": snapshot.get("change_drivers", []),
        "previous_snapshot_id": snapshot.get("prev_snapshot_ref"),
    }


def explain_json(
    snapshot: Dict[str, Any],
    metrics: Dict[str, Any],
    cfg: Dict[str, Any],
    cfg_source: str,
    cfg_path: Optional[str],
) -> str:
    payload = build_explain_payload(snapshot, metrics, cfg, cfg_source, cfg_path)
    return json.dumps(payload, indent=2, sort_keys=True)
