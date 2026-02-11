from __future__ import annotations

from typing import Any, Dict, Optional

import yaml

from .resources import read_text

REQUIRED_CONFIG_PATHS = [
    ("thresholds", "trend"),
    ("thresholds", "vol"),
    ("thresholds", "risk"),
    ("thresholds", "transition"),
    ("thresholds", "transition", "disagreement_weights"),
    ("confidence", "vote_weights"),
    ("confidence", "penalties"),
    ("confidence", "bounds"),
    ("units",),
    ("defaults_policy",),
    ("thresholds", "trend", "trend_score_pass"),
    ("thresholds", "trend", "score_weights"),
]


def load_regime_config(path: Optional[str] = None) -> Dict[str, Any]:
    """Load regime configuration from a YAML file or packaged default."""
    if path:
        with open(path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    else:
        data = yaml.safe_load(read_text("regime_v1.yaml"))
    if data is None:
        raise ValueError("Regime config is empty or invalid YAML.")
    return data


def _normalize_numeric(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize_numeric(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_normalize_numeric(item) for item in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return float(value)
    return value


def validate_regime_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Validate required keys for the regime config.

    Returns a normalized copy with numeric values cast to float when possible.
    """
    for path in REQUIRED_CONFIG_PATHS:
        cursor = cfg
        for key in path:
            if key not in cursor:
                raise KeyError(f"Missing config key: {'.'.join(path)}")
            cursor = cursor[key]

    score_weights = cfg["thresholds"]["trend"]["score_weights"]
    for key in ("position", "slope", "chop"):
        if key not in score_weights:
            raise KeyError(f"Missing config key: thresholds.trend.score_weights.{key}")
    if sum(score_weights.values()) <= 0:
        raise ValueError("trend score_weights must sum to a positive value.")

    disagreement_weights = cfg["thresholds"]["transition"]["disagreement_weights"]
    for key in ("trend_not_passed", "risk_neutral", "vol_high", "recent_change"):
        if key not in disagreement_weights:
            raise KeyError(
                f"Missing config key: thresholds.transition.disagreement_weights.{key}"
            )

    normalized = _normalize_numeric(cfg)
    return normalized
