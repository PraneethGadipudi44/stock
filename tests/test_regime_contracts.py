from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

import jsonschema

from core.regime import engine
from core.regime.constants import RESERVED_METRICS_KEYS
from core.regime.config import load_regime_config, validate_regime_config
from core.regime.models import (
    RiskSignalVote,
    TrendSignalVote,
    VolSignalVote,
    format_as_of_ts,
)


def _snapshot_to_dict(snapshot):
    extra = _metrics_extra_for_payload(snapshot.metrics_snapshot.extra)
    payload = {
        "snapshot_id": snapshot.snapshot_id,
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


def _metrics_extra_for_payload(extra):
    return {key: value for key, value in extra.items() if key not in RESERVED_METRICS_KEYS}


def test_regime_snapshot_schema_and_change_drivers_sorted(monkeypatch):
    def stub_trend(metrics, cfg):
        return TrendSignalVote(vote="trend_up", score=0.7, threshold=60.0, passed=True)

    def stub_vol(metrics, cfg):
        return VolSignalVote(vote="normal", score=0.4, threshold=80.0, passed=False)

    def stub_risk(metrics, cfg):
        return RiskSignalVote(vote="risk_on", score=0.8, threshold=1.0, passed=True)

    def stub_confidence(votes, metrics, cfg):
        return 55.0

    def stub_market_phase(votes, metrics, cfg):
        return "trend_up"

    def stub_regime_changed(current, previous):
        return True, "shift", ("trend_vote_shift", "risk_vote_shift")

    monkeypatch.setattr(engine, "compute_trend_vote", stub_trend)
    monkeypatch.setattr(engine, "compute_vol_vote", stub_vol)
    monkeypatch.setattr(engine, "compute_risk_vote", stub_risk)
    monkeypatch.setattr(engine, "compute_confidence", stub_confidence)
    monkeypatch.setattr(engine, "compute_market_phase", stub_market_phase)
    monkeypatch.setattr(engine, "compute_regime_changed", stub_regime_changed)

    metrics = {"synthetic": True}
    meta = {
        "as_of_ts": "2026-02-05T13:30:00Z",
        "session": "open",
        "engine_version": "regime_v1",
        "universe": "US_EQ_ETF",
        "benchmarks": ["SPY", "QQQ", "IWM"],
        "reasoning": ["Trend up", "Risk on", "Vol normal"],
        "metrics_snapshot": {
            "vote_disagreement_score": 0.2,
            "recent_change_window_days": 5,
            "extra_metric": 1.0,
        },
        "inputs_hash": "abc12345",
    }
    cfg = validate_regime_config(
        load_regime_config(str(ROOT / "config" / "regime_v1.yaml"))
    )

    snapshot = engine.build_regime_snapshot(metrics, meta, cfg)
    assert snapshot.change_drivers == sorted(snapshot.change_drivers)

    schema_path = ROOT / "contracts" / "regime_snapshot.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.validate(_snapshot_to_dict(snapshot), schema)


def test_build_regime_snapshot_computes_disagreement_when_missing(monkeypatch):
    def stub_trend(metrics, cfg):
        return TrendSignalVote(vote="trend_up", score=40.0, threshold=65.0, passed=False)

    def stub_vol(metrics, cfg):
        return VolSignalVote(vote="high", score=90.0, threshold=80.0, passed=True)

    def stub_risk(metrics, cfg):
        return RiskSignalVote(vote="neutral", score=0.0, threshold=1.0, passed=False)

    def stub_confidence(votes, metrics, cfg):
        return 40.0

    def stub_market_phase(votes, metrics, cfg):
        return "transition"

    def stub_regime_changed(current, previous):
        return False, "no_change", ()

    monkeypatch.setattr(engine, "compute_trend_vote", stub_trend)
    monkeypatch.setattr(engine, "compute_vol_vote", stub_vol)
    monkeypatch.setattr(engine, "compute_risk_vote", stub_risk)
    monkeypatch.setattr(engine, "compute_confidence", stub_confidence)
    monkeypatch.setattr(engine, "compute_market_phase", stub_market_phase)
    monkeypatch.setattr(engine, "compute_regime_changed", stub_regime_changed)

    cfg = validate_regime_config(
        load_regime_config(str(ROOT / "config" / "regime_v1.yaml"))
    )
    metrics = {"synthetic": True}
    meta = {
        "as_of_ts": "2026-02-05T13:30:00Z",
        "session": "open",
        "engine_version": "regime_v1",
        "universe": "US_EQ_ETF",
        "benchmarks": ["SPY", "QQQ", "IWM"],
        "reasoning": ["Trend weak", "Risk neutral", "Vol high"],
        "metrics_snapshot": {
            "recent_change_window_days": 5,
        },
        "inputs_hash": "abc12345",
    }

    snapshot = engine.build_regime_snapshot(metrics, meta, cfg)
    assert 0.0 <= snapshot.metrics_snapshot.vote_disagreement_score <= 1.0


def test_build_regime_snapshot_preserves_disagreement_when_provided(monkeypatch):
    def stub_trend(metrics, cfg):
        return TrendSignalVote(vote="trend_up", score=70.0, threshold=65.0, passed=True)

    def stub_vol(metrics, cfg):
        return VolSignalVote(vote="normal", score=40.0, threshold=80.0, passed=False)

    def stub_risk(metrics, cfg):
        return RiskSignalVote(vote="risk_on", score=2.0, threshold=1.0, passed=True)

    def stub_confidence(votes, metrics, cfg):
        return 60.0

    def stub_market_phase(votes, metrics, cfg):
        return "trend_up"

    def stub_regime_changed(current, previous):
        return False, "no_change", ()

    monkeypatch.setattr(engine, "compute_trend_vote", stub_trend)
    monkeypatch.setattr(engine, "compute_vol_vote", stub_vol)
    monkeypatch.setattr(engine, "compute_risk_vote", stub_risk)
    monkeypatch.setattr(engine, "compute_confidence", stub_confidence)
    monkeypatch.setattr(engine, "compute_market_phase", stub_market_phase)
    monkeypatch.setattr(engine, "compute_regime_changed", stub_regime_changed)

    cfg = validate_regime_config(
        load_regime_config(str(ROOT / "config" / "regime_v1.yaml"))
    )
    metrics = {"synthetic": True}
    meta = {
        "as_of_ts": "2026-02-05T13:30:00Z",
        "session": "open",
        "engine_version": "regime_v1",
        "universe": "US_EQ_ETF",
        "benchmarks": ["SPY", "QQQ", "IWM"],
        "reasoning": ["Trend up", "Risk on", "Vol normal"],
        "metrics_snapshot": {
            "vote_disagreement_score": 0.15,
            "recent_change_window_days": 20,
        },
    }

    snapshot = engine.build_regime_snapshot(metrics, meta, cfg)
    internal = snapshot.metrics_snapshot.extra.get("vote_disagreement_score_internal")
    assert snapshot.metrics_snapshot.vote_disagreement_score == max(0.15, internal)
    assert (
        snapshot.metrics_snapshot.extra.get("vote_disagreement_score_provided")
        == 0.15
    )
    assert internal is not None


def test_build_regime_snapshot_disagreement_clamped(monkeypatch):
    def stub_trend(metrics, cfg):
        return TrendSignalVote(vote="trend_up", score=40.0, threshold=65.0, passed=False)

    def stub_vol(metrics, cfg):
        return VolSignalVote(vote="high", score=90.0, threshold=80.0, passed=True)

    def stub_risk(metrics, cfg):
        return RiskSignalVote(vote="neutral", score=0.0, threshold=1.0, passed=False)

    def stub_confidence(votes, metrics, cfg):
        return 40.0

    def stub_market_phase(votes, metrics, cfg):
        return "transition"

    def stub_regime_changed(current, previous):
        return False, "no_change", ()

    monkeypatch.setattr(engine, "compute_trend_vote", stub_trend)
    monkeypatch.setattr(engine, "compute_vol_vote", stub_vol)
    monkeypatch.setattr(engine, "compute_risk_vote", stub_risk)
    monkeypatch.setattr(engine, "compute_confidence", stub_confidence)
    monkeypatch.setattr(engine, "compute_market_phase", stub_market_phase)
    monkeypatch.setattr(engine, "compute_regime_changed", stub_regime_changed)

    cfg = validate_regime_config(
        load_regime_config(str(ROOT / "config" / "regime_v1.yaml"))
    )
    metrics = {"synthetic": True}
    meta = {
        "as_of_ts": "2026-02-05T13:30:00Z",
        "session": "open",
        "engine_version": "regime_v1",
        "universe": "US_EQ_ETF",
        "benchmarks": ["SPY", "QQQ", "IWM"],
        "reasoning": ["Trend weak", "Risk neutral", "Vol high"],
        "metrics_snapshot": {
            "vote_disagreement_score": 1.5,
            "recent_change_window_days": 5,
        },
    }

    snapshot = engine.build_regime_snapshot(metrics, meta, cfg)
    assert 0.0 <= snapshot.metrics_snapshot.vote_disagreement_score <= 1.0


def test_metrics_snapshot_extra_reserved_keys_do_not_override(monkeypatch):
    def stub_trend(metrics, cfg):
        return TrendSignalVote(vote="trend_up", score=70.0, threshold=65.0, passed=True)

    def stub_vol(metrics, cfg):
        return VolSignalVote(vote="normal", score=40.0, threshold=80.0, passed=False)

    def stub_risk(metrics, cfg):
        return RiskSignalVote(vote="risk_on", score=2.0, threshold=1.0, passed=True)

    def stub_confidence(votes, metrics, cfg):
        return 60.0

    def stub_market_phase(votes, metrics, cfg):
        return "trend_up"

    def stub_regime_changed(current, previous):
        return False, "no_change", ()

    monkeypatch.setattr(engine, "compute_trend_vote", stub_trend)
    monkeypatch.setattr(engine, "compute_vol_vote", stub_vol)
    monkeypatch.setattr(engine, "compute_risk_vote", stub_risk)
    monkeypatch.setattr(engine, "compute_confidence", stub_confidence)
    monkeypatch.setattr(engine, "compute_market_phase", stub_market_phase)
    monkeypatch.setattr(engine, "compute_regime_changed", stub_regime_changed)

    cfg = validate_regime_config(
        load_regime_config(str(ROOT / "config" / "regime_v1.yaml"))
    )
    metrics = {"synthetic": True}
    meta = {
        "as_of_ts": "2026-02-05T13:30:00Z",
        "session": "open",
        "engine_version": "regime_v1",
        "universe": "US_EQ_ETF",
        "benchmarks": ["SPY", "QQQ", "IWM"],
        "reasoning": ["Trend up", "Risk on", "Vol normal"],
        "metrics_snapshot": {
            "vote_disagreement_score": 0.2,
            "recent_change_window_days": 5,
        },
    }

    snapshot = engine.build_regime_snapshot(metrics, meta, cfg)
    metrics_snapshot = snapshot.metrics_snapshot.__class__(
        vote_disagreement_score=snapshot.metrics_snapshot.vote_disagreement_score,
        recent_change_window_days=snapshot.metrics_snapshot.recent_change_window_days,
        extra={
            "vote_disagreement_score": 0.0,
            "recent_change_window_days": 0,
            "foo": 1,
        },
    )
    snapshot_with_extra = snapshot.__class__(
        snapshot_id=snapshot.snapshot_id,
        as_of_ts=snapshot.as_of_ts,
        session=snapshot.session,
        engine_version=snapshot.engine_version,
        universe=snapshot.universe,
        benchmarks=snapshot.benchmarks,
        market_phase=snapshot.market_phase,
        trend_regime=snapshot.trend_regime,
        vol_regime=snapshot.vol_regime,
        risk_tone=snapshot.risk_tone,
        confidence=snapshot.confidence,
        reasoning=snapshot.reasoning,
        signal_votes=snapshot.signal_votes,
        metrics_snapshot=metrics_snapshot,
        regime_changed=snapshot.regime_changed,
        change_reason=snapshot.change_reason,
        change_drivers=snapshot.change_drivers,
        inputs_hash=snapshot.inputs_hash,
        prev_snapshot_ref=snapshot.prev_snapshot_ref,
    )
    payload = _snapshot_to_dict(snapshot_with_extra)
    metrics_payload = payload["metrics_snapshot"]

    assert (
        metrics_payload["vote_disagreement_score"]
        == snapshot.metrics_snapshot.vote_disagreement_score
    )
    assert (
        metrics_payload["recent_change_window_days"]
        == snapshot.metrics_snapshot.recent_change_window_days
    )
    assert metrics_payload.get("foo") == 1
