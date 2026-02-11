from __future__ import annotations

from pathlib import Path

import pytest

from core.regime.config import load_regime_config, validate_regime_config
from core.regime.metrics_builder import MetricsBuildError, build_metrics_from_prices
from core.regime.prices_io import read_prices_csv, rows_to_records

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


def _cfg() -> dict:
    return validate_regime_config(load_regime_config("tests/fixtures/regime_test_cfg.yaml"))


def _rows(name: str):
    root = Path(__file__).resolve().parents[1]
    path = root / "tests" / "fixtures" / name
    rows = read_prices_csv(str(path))
    return rows_to_records(rows)


def test_missing_days_detected():
    cfg = _cfg()
    rows = _rows("prices_missing_days.csv")
    with pytest.raises(MetricsBuildError, match="Missing days for .*gap"):
        build_metrics_from_prices(rows, cfg)


def test_missing_required_ticker_detected():
    cfg = _cfg()
    rows = _rows("prices_missing_ticker.csv")
    with pytest.raises(MetricsBuildError, match="required_tickers"):
        build_metrics_from_prices(rows, cfg)


def test_overlap_short_detected():
    cfg = _cfg()
    rows = _rows("prices_overlap_short.csv")
    with pytest.raises(
        MetricsBuildError, match="Insufficient overlap for hyg_lqd_rs_20d.*lookback 5.*need 6"
    ):
        build_metrics_from_prices(rows, cfg)


def test_extra_ticker_ignored():
    cfg = _cfg()
    rows = _rows("prices_extra_ticker_sparse.csv")
    metrics = build_metrics_from_prices(rows, cfg)
    assert set(metrics.keys()) == REQUIRED_KEYS


def test_weekend_gap_ok():
    cfg = _cfg()
    rows = _rows("prices_weekend_gap_ok.csv")
    metrics = build_metrics_from_prices(rows, cfg)
    assert set(metrics.keys()) == REQUIRED_KEYS


@pytest.mark.parametrize(
    "fixture_name",
    [
        "prices_vol_spike.csv",
        "prices_credit_diverge.csv",
        "prices_trend_break.csv",
    ],
)
def test_edge_case_fixtures_ok(fixture_name: str):
    cfg = _cfg()
    rows = _rows(fixture_name)
    metrics = build_metrics_from_prices(rows, cfg)
    assert set(metrics.keys()) == REQUIRED_KEYS
