from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional


Session = Literal["premarket", "open", "midday", "close", "afterhours"]
Universe = Literal["US_EQ_ETF"]

TrendRegime = Literal["trend_up", "trend_down", "range"]
VolRegime = Literal["low", "normal", "high"]
RiskTone = Literal["risk_on", "neutral", "risk_off"]
MarketPhase = Literal["trend_up", "trend_down", "range", "transition"]

ChangeDriver = Literal[
    "trend_vote_shift",
    "vol_vote_shift",
    "risk_vote_shift",
    "breadth_shift",
    "credit_shift",
    "signal_disagreement",
    "recent_change_window",
    "market_phase_shift",
]


@dataclass(frozen=True)
class TrendSignalVote:
    vote: TrendRegime
    score: float
    threshold: float
    passed: bool


@dataclass(frozen=True)
class VolSignalVote:
    vote: VolRegime
    score: float
    threshold: float
    passed: bool


@dataclass(frozen=True)
class RiskSignalVote:
    vote: RiskTone
    score: float
    threshold: float
    passed: bool


@dataclass(frozen=True)
class SignalVotes:
    trend: TrendSignalVote
    vol: VolSignalVote
    risk: RiskSignalVote


@dataclass(frozen=True)
class MetricsSnapshot:
    vote_disagreement_score: float
    recent_change_window_days: int
    extra: Dict[str, Any] = field(default_factory=dict)


def parse_as_of_ts(value: str) -> datetime:
    """Parse an ISO-8601 timestamp to datetime.

    TODO: enforce UTC normalization at the ingestion boundary.
    """
    if value.endswith("Z"):
        value = f"{value[:-1]}+00:00"
    return datetime.fromisoformat(value)


def format_as_of_ts(value: datetime) -> str:
    """Format a datetime as ISO-8601 for serialization."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class RegimeSnapshot:
    snapshot_id: str
    as_of_ts: datetime
    session: Session
    engine_version: str
    universe: Universe
    benchmarks: List[str]
    market_phase: MarketPhase
    trend_regime: TrendRegime
    vol_regime: VolRegime
    risk_tone: RiskTone
    confidence: float
    reasoning: List[str]
    signal_votes: SignalVotes
    metrics_snapshot: MetricsSnapshot
    regime_changed: bool
    change_reason: str
    change_drivers: List[ChangeDriver]
    inputs_hash: Optional[str] = None
    prev_snapshot_ref: Optional[str] = None
