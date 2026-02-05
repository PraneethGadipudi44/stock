from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from core.regime.config import load_regime_config, validate_regime_config


def test_regime_config_load_and_validate():
    path = ROOT / "config" / "regime_v1.yaml"
    cfg = load_regime_config(str(path))
    normalized = validate_regime_config(cfg)

    assert normalized["defaults_policy"] == "conservative"
    assert "thresholds" in normalized
    assert "confidence" in normalized
    assert "units" in normalized


def test_regime_config_missing_trend_score_pass():
    path = ROOT / "config" / "regime_v1.yaml"
    cfg = load_regime_config(str(path))
    cfg["thresholds"]["trend"].pop("trend_score_pass", None)

    with pytest.raises(KeyError):
        validate_regime_config(cfg)


def test_regime_config_missing_score_weights():
    path = ROOT / "config" / "regime_v1.yaml"
    cfg = load_regime_config(str(path))
    cfg["thresholds"]["trend"].pop("score_weights", None)

    with pytest.raises(KeyError):
        validate_regime_config(cfg)


def test_regime_config_missing_disagreement_weights():
    path = ROOT / "config" / "regime_v1.yaml"
    cfg = load_regime_config(str(path))
    cfg["thresholds"]["transition"].pop("disagreement_weights", None)

    with pytest.raises(KeyError):
        validate_regime_config(cfg)


def test_regime_config_missing_disagreement_weight_key():
    path = ROOT / "config" / "regime_v1.yaml"
    cfg = load_regime_config(str(path))
    cfg["thresholds"]["transition"]["disagreement_weights"].pop(
        "trend_not_passed", None
    )

    with pytest.raises(KeyError):
        validate_regime_config(cfg)
