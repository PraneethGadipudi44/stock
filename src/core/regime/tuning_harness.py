from __future__ import annotations

import json
from typing import Dict, List, Optional

from .run_snapshot import run_snapshot


def _base_meta(scenario: str) -> Dict[str, object]:
    return {
        "as_of_ts": "2026-02-05T13:30:00Z",
        "session": "open",
        "engine_version": "regime_v1",
        "universe": "US_EQ_ETF",
        "benchmarks": ["SPY", "QQQ", "IWM"],
        "reasoning": ["Synthetic scenario", "Tuning harness", scenario],
        "metrics_snapshot": {
            "recent_change_window_days": 20,
        },
    }


def _scenarios() -> List[Dict[str, object]]:
    return [
        {
            "name": "trend_up_normal",
            "metrics": {
                "basket_price_above_50dma_pct": 80.0,
                "basket_price_above_200dma_pct": 70.0,
                "basket_ma50_slope_20d": 2.0,
                "chop_score": 30.0,
                "realized_vol_20d_pct": 40.0,
                "vix_pct": 35.0,
                "hyg_lqd_rs_20d": 2.0,
                "spy_tlt_rs_20d": 1.5,
            },
        },
        {
            "name": "trend_down_normal",
            "metrics": {
                "basket_price_above_50dma_pct": 20.0,
                "basket_price_above_200dma_pct": 25.0,
                "basket_ma50_slope_20d": -2.0,
                "chop_score": 30.0,
                "realized_vol_20d_pct": 40.0,
                "vix_pct": 35.0,
                "hyg_lqd_rs_20d": -2.0,
                "spy_tlt_rs_20d": -1.5,
            },
        },
        {
            "name": "range_choppy",
            "metrics": {
                "basket_price_above_50dma_pct": 55.0,
                "basket_price_above_200dma_pct": 52.0,
                "basket_ma50_slope_20d": 0.2,
                "chop_score": 80.0,
                "realized_vol_20d_pct": 45.0,
                "vix_pct": 40.0,
                "hyg_lqd_rs_20d": 0.2,
                "spy_tlt_rs_20d": -0.1,
            },
        },
        {
            "name": "transition_disagreement",
            "metrics": {
                "basket_price_above_50dma_pct": 65.0,
                "basket_price_above_200dma_pct": 60.0,
                "basket_ma50_slope_20d": 0.5,
                "chop_score": 45.0,
                "realized_vol_20d_pct": 85.0,
                "vix_pct": 90.0,
                "hyg_lqd_rs_20d": 0.1,
                "spy_tlt_rs_20d": -0.2,
            },
        },
        {
            "name": "risk_off_vol_high",
            "metrics": {
                "basket_price_above_50dma_pct": 35.0,
                "basket_price_above_200dma_pct": 30.0,
                "basket_ma50_slope_20d": -1.5,
                "chop_score": 50.0,
                "realized_vol_20d_pct": 90.0,
                "vix_pct": 85.0,
                "hyg_lqd_rs_20d": -2.0,
                "spy_tlt_rs_20d": -2.0,
            },
        },
        {
            "name": "vol_low_risk_on",
            "metrics": {
                "basket_price_above_50dma_pct": 75.0,
                "basket_price_above_200dma_pct": 70.0,
                "basket_ma50_slope_20d": 1.5,
                "chop_score": 35.0,
                "realized_vol_20d_pct": 10.0,
                "vix_pct": 12.0,
                "hyg_lqd_rs_20d": 1.8,
                "spy_tlt_rs_20d": 1.2,
            },
        },
        {
            "name": "neutral_risk",
            "metrics": {
                "basket_price_above_50dma_pct": 55.0,
                "basket_price_above_200dma_pct": 50.0,
                "basket_ma50_slope_20d": 0.3,
                "chop_score": 45.0,
                "realized_vol_20d_pct": 50.0,
                "vix_pct": 50.0,
                "hyg_lqd_rs_20d": 0.2,
                "spy_tlt_rs_20d": -0.1,
            },
        },
        {
            "name": "trend_up_vol_high",
            "metrics": {
                "basket_price_above_50dma_pct": 80.0,
                "basket_price_above_200dma_pct": 70.0,
                "basket_ma50_slope_20d": 2.0,
                "chop_score": 30.0,
                "realized_vol_20d_pct": 85.0,
                "vix_pct": 88.0,
                "hyg_lqd_rs_20d": 1.5,
                "spy_tlt_rs_20d": 1.0,
            },
        },
        {
            "name": "trend_up_low_score_borderline",
            "metrics": {
                "basket_price_above_50dma_pct": 60.0,
                "basket_price_above_200dma_pct": 60.0,
                "basket_ma50_slope_20d": 1.0,
                "chop_score": 60.0,
                "realized_vol_20d_pct": 50.0,
                "vix_pct": 50.0,
                "hyg_lqd_rs_20d": 0.2,
                "spy_tlt_rs_20d": 0.1,
            },
        },
        {
            "name": "trend_down_low_score_borderline",
            "metrics": {
                "basket_price_above_50dma_pct": 40.0,
                "basket_price_above_200dma_pct": 40.0,
                "basket_ma50_slope_20d": -1.0,
                "chop_score": 60.0,
                "realized_vol_20d_pct": 50.0,
                "vix_pct": 50.0,
                "hyg_lqd_rs_20d": -0.2,
                "spy_tlt_rs_20d": -0.1,
            },
        },
        {
            "name": "chop_high_borderline",
            "metrics": {
                "basket_price_above_50dma_pct": 55.0,
                "basket_price_above_200dma_pct": 55.0,
                "basket_ma50_slope_20d": 0.2,
                "chop_score": 61.8,
                "realized_vol_20d_pct": 45.0,
                "vix_pct": 45.0,
                "hyg_lqd_rs_20d": 0.1,
                "spy_tlt_rs_20d": -0.1,
            },
        },
        {
            "name": "chop_low_borderline",
            "metrics": {
                "basket_price_above_50dma_pct": 55.0,
                "basket_price_above_200dma_pct": 55.0,
                "basket_ma50_slope_20d": 0.2,
                "chop_score": 38.2,
                "realized_vol_20d_pct": 45.0,
                "vix_pct": 45.0,
                "hyg_lqd_rs_20d": 0.1,
                "spy_tlt_rs_20d": -0.1,
            },
        },
        {
            "name": "mixed_up_vol_high_risk_neutral",
            "metrics": {
                "basket_price_above_50dma_pct": 75.0,
                "basket_price_above_200dma_pct": 70.0,
                "basket_ma50_slope_20d": 1.5,
                "chop_score": 35.0,
                "realized_vol_20d_pct": 70.0,
                "vix_pct": 80.0,
                "hyg_lqd_rs_20d": 0.2,
                "spy_tlt_rs_20d": -0.1,
            },
        },
        {
            "name": "mixed_down_vol_normal_risk_on",
            "metrics": {
                "basket_price_above_50dma_pct": 30.0,
                "basket_price_above_200dma_pct": 30.0,
                "basket_ma50_slope_20d": -1.5,
                "chop_score": 35.0,
                "realized_vol_20d_pct": 50.0,
                "vix_pct": 50.0,
                "hyg_lqd_rs_20d": 1.0,
                "spy_tlt_rs_20d": 1.0,
            },
            "meta": {"metrics_snapshot": {"vote_disagreement_score": 0.15}},
        },
        {
            "name": "vol_high_borderline_realized_risk_off",
            "metrics": {
                "basket_price_above_50dma_pct": 55.0,
                "basket_price_above_200dma_pct": 50.0,
                "basket_ma50_slope_20d": 0.2,
                "chop_score": 45.0,
                "realized_vol_20d_pct": 80.0,
                "vix_pct": 50.0,
                "hyg_lqd_rs_20d": -1.0,
                "spy_tlt_rs_20d": -1.0,
            },
        },
        {
            "name": "vol_low_borderline",
            "metrics": {
                "basket_price_above_50dma_pct": 60.0,
                "basket_price_above_200dma_pct": 60.0,
                "basket_ma50_slope_20d": 1.0,
                "chop_score": 35.0,
                "realized_vol_20d_pct": 20.0,
                "vix_pct": 20.0,
                "hyg_lqd_rs_20d": 0.2,
                "spy_tlt_rs_20d": 0.1,
            },
        },
    ]


def run_harness(cfg_path: Optional[str] = None) -> List[Dict[str, object]]:
    rows = []
    for scenario in _scenarios():
        meta = _base_meta(scenario["name"])
        meta_override = scenario.get("meta") or {}
        if "metrics_snapshot" in meta_override:
            meta_metrics = dict(meta["metrics_snapshot"])
            meta_metrics.update(meta_override["metrics_snapshot"])
            meta["metrics_snapshot"] = meta_metrics
            meta_override = dict(meta_override)
            meta_override.pop("metrics_snapshot", None)
        meta.update(meta_override)
        output = run_snapshot(scenario["metrics"], meta, cfg_path=cfg_path)
        payload = json.loads(output)
        votes = payload["signal_votes"]
        metrics_snapshot = payload["metrics_snapshot"]
        rows.append(
            {
                "scenario": scenario["name"],
                "market_phase": payload["market_phase"],
                "trend_regime": payload["trend_regime"],
                "vol_regime": payload["vol_regime"],
                "risk_tone": payload["risk_tone"],
                "confidence": payload["confidence"],
                "trend_vote": votes["trend"]["vote"],
                "vol_vote": votes["vol"]["vote"],
                "risk_vote": votes["risk"]["vote"],
                "trend_score": votes["trend"]["score"],
                "vol_score": votes["vol"]["score"],
                "risk_score": votes["risk"]["score"],
                "trend_direction_score": metrics_snapshot.get("trend_direction_score"),
                "vote_disagreement_score": metrics_snapshot[
                    "vote_disagreement_score"
                ],
                "vote_disagreement_score_internal": metrics_snapshot.get(
                    "vote_disagreement_score_internal"
                ),
                "vote_disagreement_score_provided": metrics_snapshot.get(
                    "vote_disagreement_score_provided"
                ),
            }
        )
    return rows


def run_harness_snapshots(cfg_path: Optional[str] = None) -> List[Dict[str, object]]:
    entries: List[Dict[str, object]] = []
    for scenario in _scenarios():
        meta = _base_meta(scenario["name"])
        meta_override = scenario.get("meta") or {}
        if "metrics_snapshot" in meta_override:
            meta_metrics = dict(meta["metrics_snapshot"])
            meta_metrics.update(meta_override["metrics_snapshot"])
            meta["metrics_snapshot"] = meta_metrics
            meta_override = dict(meta_override)
            meta_override.pop("metrics_snapshot", None)
        meta.update(meta_override)
        output = run_snapshot(scenario["metrics"], meta, cfg_path=cfg_path)
        payload = json.loads(output)
        entries.append(
            {
                "scenario": scenario["name"],
                "metrics": scenario["metrics"],
                "snapshot": payload,
            }
        )
    return entries
