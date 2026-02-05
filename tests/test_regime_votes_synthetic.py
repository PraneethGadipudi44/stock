from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from core.regime.config import load_regime_config, validate_regime_config
from core.regime import engine
from core.regime.engine import (
    compute_confidence,
    compute_market_phase,
    compute_risk_vote,
    compute_trend_vote,
    compute_vol_vote,
)
from core.regime.models import MetricsSnapshot, SignalVotes, TrendSignalVote, VolSignalVote, RiskSignalVote


CFG = validate_regime_config(
    load_regime_config(str(ROOT / "config" / "regime_v1.yaml"))
)


def test_trend_vote_up_synthetic():
    metrics = {
        "basket_price_above_50dma_pct": 80.0,
        "basket_price_above_200dma_pct": 75.0,
        "basket_ma50_slope_20d": 3.0,
        "chop_score": 30.0,
    }
    vote = compute_trend_vote(metrics, CFG)
    assert vote.vote == "trend_up"
    assert vote.threshold == CFG["thresholds"]["trend"]["trend_score_pass"]


def test_trend_vote_range_when_chop_high():
    metrics = {
        "basket_price_above_50dma_pct": 70.0,
        "basket_price_above_200dma_pct": 70.0,
        "basket_ma50_slope_20d": 2.0,
        "chop_score": 80.0,
    }
    vote = compute_trend_vote(metrics, CFG)
    assert vote.vote == "range"
    assert vote.passed is True
    assert vote.threshold == CFG["thresholds"]["trend"]["chop_high"]


def test_trend_vote_range_when_position_up_but_slope_weak():
    metrics = {
        "basket_price_above_50dma_pct": 70.0,
        "basket_price_above_200dma_pct": 70.0,
        "basket_ma50_slope_20d": 0.2,
        "chop_score": 50.0,
    }
    vote = compute_trend_vote(metrics, CFG)
    assert vote.vote == "range"


def test_trend_vote_actionable_requires_score_threshold():
    metrics = {
        "basket_price_above_50dma_pct": 65.0,
        "basket_price_above_200dma_pct": 65.0,
        "basket_ma50_slope_20d": 1.0,
        "chop_score": 60.0,
    }
    cfg = {
        **CFG,
        "thresholds": {
            **CFG["thresholds"],
            "trend": {
                **CFG["thresholds"]["trend"],
                "trend_score_pass": 90.0,
            },
        },
    }
    vote = compute_trend_vote(metrics, cfg)
    assert vote.vote == "trend_up"
    assert vote.passed is False


def test_vol_vote_high_synthetic():
    metrics = {
        "realized_vol_20d_pct": 90.0,
        "vix_pct": 85.0,
    }
    vote = compute_vol_vote(metrics, CFG)
    assert vote.vote == "high"


def test_vol_vote_normal_passed_false():
    metrics = {
        "realized_vol_20d_pct": 50.0,
        "vix_pct": 50.0,
    }
    vote = compute_vol_vote(metrics, CFG)
    assert vote.vote == "normal"
    assert vote.passed is False


def test_risk_vote_on_synthetic():
    metrics = {
        "hyg_lqd_rs_20d": 2.0,
        "spy_tlt_rs_20d": 2.5,
    }
    vote = compute_risk_vote(metrics, CFG)
    assert vote.vote == "risk_on"


def test_risk_vote_neutral_passed_false():
    metrics = {
        "hyg_lqd_rs_20d": 0.2,
        "spy_tlt_rs_20d": -0.1,
    }
    vote = compute_risk_vote(metrics, CFG)
    assert vote.vote == "neutral"
    assert vote.passed is False


def test_confidence_and_market_phase_synthetic():
    votes = SignalVotes(
        trend=TrendSignalVote(vote="trend_up", score=80.0, threshold=66.7, passed=True),
        vol=VolSignalVote(vote="normal", score=40.0, threshold=80.0, passed=False),
        risk=RiskSignalVote(vote="risk_on", score=2.0, threshold=1.0, passed=True),
    )
    metrics = MetricsSnapshot(vote_disagreement_score=0.1, recent_change_window_days=20)
    confidence = compute_confidence(votes, metrics, CFG)
    phase = compute_market_phase(votes, metrics, CFG)
    assert confidence >= 0
    assert phase == "trend_up"


def test_confidence_decreases_with_disagreement():
    votes = SignalVotes(
        trend=TrendSignalVote(vote="range", score=70.0, threshold=60.0, passed=True),
        vol=VolSignalVote(vote="normal", score=40.0, threshold=80.0, passed=False),
        risk=RiskSignalVote(vote="neutral", score=0.0, threshold=1.0, passed=False),
    )
    low_disagreement = MetricsSnapshot(
        vote_disagreement_score=0.1, recent_change_window_days=20
    )
    high_disagreement = MetricsSnapshot(
        vote_disagreement_score=0.9, recent_change_window_days=20
    )
    conf_low = compute_confidence(votes, low_disagreement, CFG)
    conf_high = compute_confidence(votes, high_disagreement, CFG)
    assert conf_high < conf_low


def test_confidence_higher_for_risk_on_than_neutral():
    votes_risk_on = SignalVotes(
        trend=TrendSignalVote(vote="trend_up", score=80.0, threshold=65.0, passed=True),
        vol=VolSignalVote(vote="normal", score=40.0, threshold=80.0, passed=False),
        risk=RiskSignalVote(vote="risk_on", score=2.0, threshold=1.0, passed=True),
    )
    votes_neutral = SignalVotes(
        trend=TrendSignalVote(vote="trend_up", score=80.0, threshold=65.0, passed=True),
        vol=VolSignalVote(vote="normal", score=40.0, threshold=80.0, passed=False),
        risk=RiskSignalVote(vote="neutral", score=0.2, threshold=1.0, passed=False),
    )
    metrics = MetricsSnapshot(vote_disagreement_score=0.1, recent_change_window_days=20)
    conf_on = compute_confidence(votes_risk_on, metrics, CFG)
    conf_neutral = compute_confidence(votes_neutral, metrics, CFG)
    assert conf_on > conf_neutral


def test_market_phase_transition_when_disagreement_high():
    votes = SignalVotes(
        trend=TrendSignalVote(vote="trend_up", score=80.0, threshold=66.7, passed=True),
        vol=VolSignalVote(vote="normal", score=40.0, threshold=80.0, passed=False),
        risk=RiskSignalVote(vote="risk_on", score=2.0, threshold=1.0, passed=True),
    )
    metrics = MetricsSnapshot(vote_disagreement_score=0.6, recent_change_window_days=20)
    phase = compute_market_phase(votes, metrics, CFG)
    assert phase == "transition"


def test_market_phase_transition_when_trend_not_passed_conservative():
    votes = SignalVotes(
        trend=TrendSignalVote(vote="trend_up", score=40.0, threshold=65.0, passed=False),
        vol=VolSignalVote(vote="normal", score=40.0, threshold=80.0, passed=False),
        risk=RiskSignalVote(vote="risk_on", score=2.0, threshold=1.0, passed=True),
    )
    metrics = MetricsSnapshot(vote_disagreement_score=0.1, recent_change_window_days=20)
    phase = compute_market_phase(votes, metrics, CFG)
    assert phase == "transition"


def test_vote_disagreement_weights_configurable():
    votes = SignalVotes(
        trend=TrendSignalVote(vote="trend_up", score=40.0, threshold=65.0, passed=False),
        vol=VolSignalVote(vote="high", score=90.0, threshold=80.0, passed=True),
        risk=RiskSignalVote(vote="neutral", score=0.0, threshold=1.0, passed=False),
    )
    metrics = MetricsSnapshot(vote_disagreement_score=0.0, recent_change_window_days=0)

    base = engine._compute_vote_disagreement(votes, metrics, CFG)

    cfg_low = {
        **CFG,
        "thresholds": {
            **CFG["thresholds"],
            "transition": {
                **CFG["thresholds"]["transition"],
                "disagreement_weights": {
                    "trend_not_passed": 0.1,
                    "risk_neutral": 0.1,
                    "vol_high": 0.1,
                    "recent_change": 0.1,
                },
            },
        },
    }
    low = engine._compute_vote_disagreement(votes, metrics, cfg_low)

    assert low == 0.4
    assert base >= low
