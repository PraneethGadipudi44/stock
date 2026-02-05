from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from core.regime.config import load_regime_config, validate_regime_config
from core.regime.engine import build_regime_snapshot


def test_regime_invariants_randomized():
    cfg = validate_regime_config(
        load_regime_config(str(ROOT / "config" / "regime_v1.yaml"))
    )
    bounds = cfg["confidence"]["bounds"]

    rng = random.Random(42)
    for i in range(50):
        metrics = {
            "basket_price_above_50dma_pct": rng.uniform(0, 100),
            "basket_price_above_200dma_pct": rng.uniform(0, 100),
            "basket_ma50_slope_20d": rng.uniform(-10, 10),
            "chop_score": rng.uniform(0, 100),
            "realized_vol_20d_pct": rng.uniform(0, 100),
            "vix_pct": rng.uniform(0, 100),
            "hyg_lqd_rs_20d": rng.uniform(-5, 5),
            "spy_tlt_rs_20d": rng.uniform(-5, 5),
        }
        meta = {
            "as_of_ts": "2026-02-05T13:30:00Z",
            "session": "open",
            "engine_version": "regime_v1",
            "universe": "US_EQ_ETF",
            "benchmarks": ["SPY", "QQQ", "IWM"],
            "reasoning": ["Synthetic", "Invariant", f"Run {i}"],
            "metrics_snapshot": {
                "recent_change_window_days": rng.randint(0, 30),
            },
        }

        snapshot = build_regime_snapshot(metrics, meta, cfg)

        assert 0.0 <= snapshot.metrics_snapshot.vote_disagreement_score <= 1.0
        assert bounds["min"] <= snapshot.confidence <= bounds["max"]
        assert snapshot.change_drivers == sorted(snapshot.change_drivers)
        assert len(snapshot.change_drivers) == len(set(snapshot.change_drivers))
