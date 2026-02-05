from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

from .constants import RESERVED_METRICS_KEYS
from .models import (
    ChangeDriver,
    MarketPhase,
    MetricsSnapshot,
    RegimeSnapshot,
    SignalVotes,
    parse_as_of_ts,
    RiskSignalVote,
    TrendSignalVote,
    VolSignalVote,
)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value


def _normalize(value: float, low: float, high: float) -> float:
    if high == low:
        return 0.0
    return _clamp((value - low) / (high - low))


def _compute_vote_disagreement(
    votes: SignalVotes, metrics: MetricsSnapshot, cfg: Dict[str, Any]
) -> float:
    transition_cfg = cfg["thresholds"]["transition"]
    weights = transition_cfg["disagreement_weights"]
    score = 0.0

    if votes.trend.vote != "range" and not votes.trend.passed:
        score += weights["trend_not_passed"]
    if votes.risk.vote == "neutral":
        score += weights["risk_neutral"]
    if votes.vol.vote == "high":
        score += weights["vol_high"]
    if (
        metrics.recent_change_window_days
        <= transition_cfg["recent_change_window_days_cutoff"]
    ):
        score += weights["recent_change"]

    return _clamp(score)


def _risk_strength(vote: RiskSignalVote, cfg: Dict[str, Any]) -> float:
    risk_cfg = cfg["thresholds"]["risk"]
    pos_thr = min(risk_cfg["hyg_lqd_rs_20d_pos"], risk_cfg["spy_tlt_rs_20d_pos"])
    neg_thr = min(
        abs(risk_cfg["hyg_lqd_rs_20d_neg"]),
        abs(risk_cfg["spy_tlt_rs_20d_neg"]),
    )
    denom = neg_thr if vote.vote == "risk_off" else pos_thr
    if not denom:
        return 0.0
    return _clamp(abs(vote.score) / denom)


def _sanitize_metrics_extra(metrics_snapshot_meta: Dict[str, Any]) -> Dict[str, Any]:
    reserved_required = RESERVED_METRICS_KEYS
    reserved_extra = {
        "vote_disagreement_score_internal",
        "vote_disagreement_score_provided",
    }
    sanitized: Dict[str, Any] = {}
    for key, value in metrics_snapshot_meta.items():
        if key in reserved_required:
            continue
        if key in reserved_extra:
            sanitized[f"extra_reserved_{key}"] = value
            continue
        sanitized[key] = value
    return sanitized


def compute_trend_vote(metrics: Dict[str, Any], cfg: Dict[str, Any]) -> TrendSignalVote:
    """Compute the trend vote from normalized metrics.

    Expected inputs include price position, slope, and chop indicators.
    Uses only config-driven thresholds; ambiguous cases default to range.
    """
    trend_cfg = cfg["thresholds"]["trend"]
    defaults_policy = cfg.get("defaults_policy", "conservative")

    above_50 = metrics["basket_price_above_50dma_pct"]
    above_200 = metrics["basket_price_above_200dma_pct"]
    slope = metrics["basket_ma50_slope_20d"]
    chop = metrics["chop_score"]

    position_up = (
        above_50 >= trend_cfg["basket_above_50dma_up"]
        and above_200 >= trend_cfg["basket_above_200dma_up"]
    )
    position_down = (
        above_50 <= trend_cfg["basket_above_50dma_down"]
        and above_200 <= trend_cfg["basket_above_200dma_down"]
    )
    slope_up = slope >= trend_cfg["ma50_slope_20d_up"]
    slope_down = slope <= trend_cfg["ma50_slope_20d_down"]

    chop_high = chop >= trend_cfg["chop_high"]
    chop_low = chop <= trend_cfg["chop_low"]

    evidence_flags_up = [position_up, slope_up, chop_low]
    evidence_flags_down = [position_down, slope_down, chop_low]
    evidence_count = len(evidence_flags_up)
    required = 2 if defaults_policy == "conservative" else evidence_count
    up_votes = sum(evidence_flags_up)
    down_votes = sum(evidence_flags_down)

    score_weights = trend_cfg["score_weights"]
    total_weight = sum(score_weights.values()) or 1.0

    pos_up_strength = 0.5 * (
        _normalize(
            above_50,
            trend_cfg["basket_above_50dma_down"],
            trend_cfg["basket_above_50dma_up"],
        )
        + _normalize(
            above_200,
            trend_cfg["basket_above_200dma_down"],
            trend_cfg["basket_above_200dma_up"],
        )
    )
    below_50 = 100.0 - above_50
    below_200 = 100.0 - above_200
    pos_down_strength = 0.5 * (
        _normalize(
            below_50,
            100.0 - trend_cfg["basket_above_50dma_up"],
            100.0 - trend_cfg["basket_above_50dma_down"],
        )
        + _normalize(
            below_200,
            100.0 - trend_cfg["basket_above_200dma_up"],
            100.0 - trend_cfg["basket_above_200dma_down"],
        )
    )

    slope_up_strength = _normalize(
        slope,
        trend_cfg["ma50_slope_20d_down"],
        trend_cfg["ma50_slope_20d_up"],
    )
    slope_down_strength = _normalize(
        -slope,
        -trend_cfg["ma50_slope_20d_up"],
        -trend_cfg["ma50_slope_20d_down"],
    )

    chop_strength = 1.0 - _normalize(
        chop, trend_cfg["chop_low"], trend_cfg["chop_high"]
    )
    chop_strength = _clamp(chop_strength)

    trend_up_score = 100.0 * (
        score_weights["position"] * pos_up_strength
        + score_weights["slope"] * slope_up_strength
        + score_weights["chop"] * chop_strength
    ) / total_weight

    trend_down_score = 100.0 * (
        score_weights["position"] * pos_down_strength
        + score_weights["slope"] * slope_down_strength
        + score_weights["chop"] * chop_strength
    ) / total_weight

    if chop_high:
        # Range due to chop: threshold reflects chop_high.
        return TrendSignalVote(
            vote="range",
            score=chop,
            threshold=trend_cfg["chop_high"],
            passed=True,
        )

    if up_votes >= required and down_votes >= required:
        return TrendSignalVote(
            vote="range",
            score=chop,
            threshold=trend_cfg["chop_low"],
            passed=False,
        )

    if up_votes >= required:
        trend_score_pass = trend_cfg["trend_score_pass"]
        return TrendSignalVote(
            vote="trend_up",
            score=trend_up_score,
            threshold=trend_score_pass,
            passed=trend_up_score >= trend_score_pass,
        )

    if down_votes >= required:
        trend_score_pass = trend_cfg["trend_score_pass"]
        return TrendSignalVote(
            vote="trend_down",
            score=trend_down_score,
            threshold=trend_score_pass,
            passed=trend_down_score >= trend_score_pass,
        )

    # Range without chop_high: threshold reflects chop_low (non-actionable).
    return TrendSignalVote(
        vote="range",
        score=chop,
        threshold=trend_cfg["chop_low"],
        passed=False,
    )


def compute_vol_vote(metrics: Dict[str, Any], cfg: Dict[str, Any]) -> VolSignalVote:
    """Compute the volatility vote from normalized metrics.

    Expected inputs include realized volatility percentile and VIX percentile.
    Uses only config-driven thresholds; ambiguous cases default to normal.
    """
    vol_cfg = cfg["thresholds"]["vol"]
    vix_pct = metrics["vix_pct"]
    realized_pct = metrics["realized_vol_20d_pct"]

    vix_high = vol_cfg["vix_pct_high"]
    vix_low = vol_cfg["vix_pct_low"]
    realized_high = vol_cfg["realized_vol_20d_pct_high"]
    realized_low = vol_cfg["realized_vol_20d_pct_low"]

    is_high = vix_pct >= vix_high or realized_pct >= realized_high
    is_low = vix_pct <= vix_low and realized_pct <= realized_low
    score = max(vix_pct, realized_pct)

    if is_high:
        threshold = min(vix_high, realized_high)
        return VolSignalVote(vote="high", score=score, threshold=threshold, passed=True)

    if is_low:
        threshold = max(vix_low, realized_low)
        return VolSignalVote(vote="low", score=score, threshold=threshold, passed=True)

    threshold = min(vix_high, realized_high)
    return VolSignalVote(vote="normal", score=score, threshold=threshold, passed=False)


def compute_risk_vote(metrics: Dict[str, Any], cfg: Dict[str, Any]) -> RiskSignalVote:
    """Compute the risk tone vote from normalized metrics.

    Expected inputs include credit and equity risk proxies.
    Uses only config-driven thresholds; ambiguous cases default to neutral.
    """
    risk_cfg = cfg["thresholds"]["risk"]
    hyg_rs = metrics["hyg_lqd_rs_20d"]
    spy_rs = metrics["spy_tlt_rs_20d"]

    hyg_pos = risk_cfg["hyg_lqd_rs_20d_pos"]
    hyg_neg = risk_cfg["hyg_lqd_rs_20d_neg"]
    spy_pos = risk_cfg["spy_tlt_rs_20d_pos"]
    spy_neg = risk_cfg["spy_tlt_rs_20d_neg"]

    credit_pos = hyg_rs >= hyg_pos
    credit_neg = hyg_rs <= hyg_neg
    equity_pos = spy_rs >= spy_pos
    equity_neg = spy_rs <= spy_neg

    min_abs = min(abs(hyg_rs), abs(spy_rs))
    sign = 0.0
    if hyg_rs + spy_rs > 0:
        sign = 1.0
    elif hyg_rs + spy_rs < 0:
        sign = -1.0

    if credit_pos and equity_pos:
        return RiskSignalVote(
            vote="risk_on",
            score=min_abs,
            threshold=min(hyg_pos, spy_pos),
            passed=True,
        )

    if credit_neg and equity_neg:
        return RiskSignalVote(
            vote="risk_off",
            score=-min_abs,
            threshold=min(abs(hyg_neg), abs(spy_neg)),
            passed=True,
        )

    # For neutral, use the nearest boundary magnitude as the reference threshold.
    threshold = min(min(hyg_pos, spy_pos), min(abs(hyg_neg), abs(spy_neg)))
    return RiskSignalVote(
        vote="neutral",
        score=min_abs * sign,
        threshold=threshold,
        passed=False,
    )


def compute_confidence(
    votes: SignalVotes, metrics: MetricsSnapshot, cfg: Dict[str, Any]
) -> float:
    """Aggregate vote agreement into a confidence score.

    Confidence should be reduced for disagreement, high volatility,
    and recent regime shifts.
    """
    weights = cfg["confidence"]["vote_weights"]
    penalties = cfg["confidence"]["penalties"]
    bounds = cfg["confidence"]["bounds"]
    transition_cfg = cfg["thresholds"]["transition"]

    max_conf = bounds["max"]
    min_conf = bounds["min"]

    weight_sum = sum(weights.values()) or 1.0
    trend_strength = _clamp(abs(votes.trend.score) / 100.0)
    vol_strength = _clamp(abs(votes.vol.score) / 100.0)
    risk_strength = _risk_strength(votes.risk, cfg)

    base = max_conf * (
        weights["trend"] * trend_strength
        + weights["vol"] * vol_strength
        + weights["risk"] * risk_strength
    ) / weight_sum

    score = base

    if votes.vol.vote == "high":
        score -= penalties["vol_high"]
    if votes.risk.vote == "risk_off":
        score -= penalties["risk_off"]

    if metrics.vote_disagreement_score >= transition_cfg[
        "vote_disagreement_score_cutoff"
    ]:
        score -= penalties["transition"]

    score -= penalties["disagreement_per_point"] * metrics.vote_disagreement_score

    if (
        metrics.recent_change_window_days
        <= transition_cfg["recent_change_window_days_cutoff"]
    ):
        score -= penalties["recent_change"]

    if score < min_conf:
        return float(min_conf)
    if score > max_conf:
        return float(max_conf)
    return float(score)


def compute_market_phase(
    votes: SignalVotes, metrics: MetricsSnapshot, cfg: Dict[str, Any]
) -> MarketPhase:
    """Compute the single market phase label for strategy gating.

    Uses trend, risk, volatility votes and deterministic transition metrics.
    """
    transition_cfg = cfg["thresholds"]["transition"]
    defaults_policy = cfg.get("defaults_policy", "conservative")

    if metrics.vote_disagreement_score >= transition_cfg[
        "vote_disagreement_score_cutoff"
    ]:
        return "transition"

    if (
        metrics.recent_change_window_days
        <= transition_cfg["recent_change_window_days_cutoff"]
    ):
        return "transition"

    if defaults_policy == "conservative":
        if votes.trend.vote != "range" and not votes.trend.passed:
            return "transition"
        if votes.trend.vote != "range" and votes.risk.vote == "neutral":
            return "transition"

    if (
        votes.trend.vote == "trend_up"
        and votes.vol.vote != "high"
        and votes.risk.vote != "risk_off"
    ):
        return "trend_up"

    if votes.trend.vote == "trend_down" and votes.risk.vote != "risk_on":
        return "trend_down"

    if votes.trend.vote == "range":
        return "range"

    return "transition"


def compute_regime_changed(
    current: RegimeSnapshot, previous: Optional[RegimeSnapshot]
) -> Tuple[bool, str, Tuple[ChangeDriver, ...]]:
    """Determine if the regime changed, with reason and drivers.

    Returns (regime_changed, change_reason, change_drivers).
    """
    if previous is None:
        return False, "no_prior", ()

    drivers = []
    reasons = []

    if current.market_phase != previous.market_phase:
        drivers.append("market_phase_shift")
        reasons.append(
            f"market_phase {previous.market_phase}->{current.market_phase}"
        )

    if current.trend_regime != previous.trend_regime:
        drivers.append("trend_vote_shift")
        reasons.append(
            f"trend {previous.trend_regime}->{current.trend_regime}"
        )

    if current.vol_regime != previous.vol_regime:
        drivers.append("vol_vote_shift")
        reasons.append(f"vol {previous.vol_regime}->{current.vol_regime}")

    if current.risk_tone != previous.risk_tone:
        drivers.append("risk_vote_shift")
        reasons.append(f"risk {previous.risk_tone}->{current.risk_tone}")

    if not drivers:
        return False, "no_change", ()

    change_reason = "; ".join(reasons)
    drivers_sorted = tuple(sorted(drivers))
    return True, change_reason, drivers_sorted


def build_regime_snapshot(
    metrics: Dict[str, Any],
    meta: Dict[str, Any],
    cfg: Dict[str, Any],
    previous: Optional[RegimeSnapshot] = None,
) -> RegimeSnapshot:
    """Orchestrate vote computation and assemble a RegimeSnapshot.

    Expected meta keys:
    - as_of_ts: datetime or ISO-8601 string
    - session: Session enum string
    - engine_version: string
    - universe: Universe enum string
    - benchmarks: list of benchmark symbols
    - reasoning: list of 3-5 short bullets
    - metrics_snapshot: dict with vote_disagreement_score, recent_change_window_days,
      and optional extra metrics
    - inputs_hash: optional string
    - prev_snapshot_ref: optional string

    Expected cfg:
    - thresholds and weights from config/regime_v1.yaml (structure only)
    """
    snapshot_id = uuid4().hex

    as_of_ts = meta["as_of_ts"]
    if isinstance(as_of_ts, str):
        as_of_ts = parse_as_of_ts(as_of_ts)

    reasoning = meta["reasoning"]
    if not (3 <= len(reasoning) <= 5):
        raise ValueError("reasoning must contain between 3 and 5 items.")

    metrics_snapshot_meta = meta["metrics_snapshot"]
    extra = _sanitize_metrics_extra(metrics_snapshot_meta)

    trend_vote = compute_trend_vote(metrics, cfg)
    vol_vote = compute_vol_vote(metrics, cfg)
    risk_vote = compute_risk_vote(metrics, cfg)

    votes = SignalVotes(trend=trend_vote, vol=vol_vote, risk=risk_vote)

    if trend_vote.vote == "trend_up":
        trend_direction_score = float(trend_vote.score)
    elif trend_vote.vote == "trend_down":
        trend_direction_score = -float(trend_vote.score)
    else:
        trend_direction_score = 0.0
    extra = {**extra, "trend_direction_score": trend_direction_score}

    recent_change_window_days = metrics_snapshot_meta["recent_change_window_days"]
    temp_metrics = MetricsSnapshot(
        vote_disagreement_score=0.0,
        recent_change_window_days=recent_change_window_days,
        extra=extra,
    )
    internal_disagreement = _compute_vote_disagreement(votes, temp_metrics, cfg)

    if "vote_disagreement_score" in metrics_snapshot_meta:
        provided_disagreement = metrics_snapshot_meta["vote_disagreement_score"]
        effective_disagreement = max(provided_disagreement, internal_disagreement)
        vote_disagreement_score = _clamp(effective_disagreement)
        extra = {
            **extra,
            "vote_disagreement_score_internal": internal_disagreement,
            "vote_disagreement_score_provided": provided_disagreement,
        }
    else:
        vote_disagreement_score = _clamp(internal_disagreement)

    metrics_snapshot = MetricsSnapshot(
        vote_disagreement_score=vote_disagreement_score,
        recent_change_window_days=recent_change_window_days,
        extra=extra,
    )
    confidence = compute_confidence(votes, metrics_snapshot, cfg)
    market_phase = compute_market_phase(votes, metrics_snapshot, cfg)

    prev_snapshot_ref = meta.get("prev_snapshot_ref")
    if prev_snapshot_ref is None and previous is not None:
        prev_snapshot_ref = previous.snapshot_id

    provisional = RegimeSnapshot(
        snapshot_id=snapshot_id,
        as_of_ts=as_of_ts,
        session=meta["session"],
        engine_version=meta["engine_version"],
        universe=meta["universe"],
        benchmarks=meta["benchmarks"],
        market_phase=market_phase,
        trend_regime=trend_vote.vote,
        vol_regime=vol_vote.vote,
        risk_tone=risk_vote.vote,
        confidence=confidence,
        reasoning=reasoning,
        signal_votes=votes,
        metrics_snapshot=metrics_snapshot,
        regime_changed=False,
        change_reason="",
        change_drivers=[],
        inputs_hash=meta.get("inputs_hash"),
        prev_snapshot_ref=prev_snapshot_ref,
    )

    regime_changed, change_reason, change_drivers = compute_regime_changed(
        provisional, previous
    )

    return replace(
        provisional,
        regime_changed=regime_changed,
        change_reason=change_reason,
        change_drivers=sorted(change_drivers),
    )
