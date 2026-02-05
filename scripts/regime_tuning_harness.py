from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from core.regime.run_snapshot import run_snapshot


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
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Regime v1 tuning harness")
    parser.add_argument(
        "--cfg",
        default=str(ROOT / "config" / "regime_v1.yaml"),
        help="Path to regime config file",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Optional CSV output path. Defaults to stdout if empty.",
    )
    args = parser.parse_args()

    rows = []
    for scenario in _scenarios():
        meta = _base_meta(scenario["name"])
        output = run_snapshot(scenario["metrics"], meta, cfg_path=args.cfg)
        payload = json.loads(output)
        rows.append(
            {
                "scenario": scenario["name"],
                "market_phase": payload["market_phase"],
                "trend_regime": payload["trend_regime"],
                "vol_regime": payload["vol_regime"],
                "risk_tone": payload["risk_tone"],
                "confidence": payload["confidence"],
                "vote_disagreement_score": payload["metrics_snapshot"][
                    "vote_disagreement_score"
                ],
            }
        )

    fieldnames = [
        "scenario",
        "market_phase",
        "trend_regime",
        "vol_regime",
        "risk_tone",
        "confidence",
        "vote_disagreement_score",
    ]

    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
