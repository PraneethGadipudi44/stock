from __future__ import annotations

import math
import random
from datetime import date, timedelta

import pytest

from core.regime.config import load_regime_config, validate_regime_config
from core.regime.metrics_builder import MetricsBuildError, build_metrics_from_prices


REQUIRED_KEYS = {
    "basket_price_above_50dma_pct",
    "basket_price_above_200dma_pct",
    "basket_ma50_slope_20d",
    "chop_score",
    "realized_vol_20d_pct",
    "vix_pct",
    "hyg_lqd_rs_20d",
    "spy_tlt_rs_20d",
}


def _small_cfg() -> dict:
    cfg = validate_regime_config(load_regime_config("config/regime_v1.yaml"))
    metrics = dict(cfg["metrics"])
    metrics.update(
        {
            "sma_short_window": 5,
            "sma_long_window": 10,
            "slope_window": 3,
            "chop_window": 5,
            "vol_window": 5,
            "vol_lookback": 10,
            "vix_pct_lookback": 10,
            "rs_window": 5,
        }
    )
    cfg["metrics"] = metrics
    return cfg


def _make_prices(days: int, tickers: list[str]) -> list[dict]:
    rng = random.Random(123)
    start = date(2026, 1, 1)
    base_map = {
        "SPY": 100.0,
        "TLT": 90.0,
        "HYG": 80.0,
        "LQD": 85.0,
        "VIX": 20.0,
    }
    trend_map = {
        "SPY": 0.2,
        "TLT": -0.05,
        "HYG": 0.1,
        "LQD": 0.05,
        "VIX": 0.02,
    }
    rows = []
    for idx in range(days):
        current_date = start + timedelta(days=idx)
        for ticker in tickers:
            base = base_map[ticker]
            trend = trend_map[ticker]
            noise = rng.uniform(-0.2, 0.2)
            close = base + trend * idx + noise
            rows.append(
                {
                    "date": current_date.isoformat(),
                    "ticker": ticker,
                    "close": round(close, 6),
                }
            )
    return rows


def test_metrics_builder_outputs_keys_and_floats():
    cfg = _small_cfg()
    rows = _make_prices(40, ["SPY", "TLT", "HYG", "LQD", "VIX"])

    metrics = build_metrics_from_prices(rows, cfg)
    assert set(metrics.keys()) == REQUIRED_KEYS

    for value in metrics.values():
        assert isinstance(value, float)
        assert math.isfinite(value)

    metrics_repeat = build_metrics_from_prices(rows, cfg)
    assert metrics == metrics_repeat


def test_metrics_builder_missing_ticker_raises():
    cfg = _small_cfg()
    rows = _make_prices(40, ["SPY", "TLT", "HYG", "LQD"])

    with pytest.raises(MetricsBuildError, match="required_tickers"):
        build_metrics_from_prices(rows, cfg)


def test_metrics_builder_insufficient_history_raises():
    cfg = _small_cfg()
    rows = _make_prices(6, ["SPY", "TLT", "HYG", "LQD", "VIX"])

    with pytest.raises(MetricsBuildError):
        build_metrics_from_prices(rows, cfg)
