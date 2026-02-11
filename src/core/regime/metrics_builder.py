from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple


class MetricsBuildError(ValueError):
    """Raised when price inputs are invalid or insufficient for metrics."""


def build_metrics_from_prices(prices: "pd.DataFrame", cfg: Dict[str, Any]) -> Dict[str, float]:
    """Build normalized regime metrics from daily price inputs.

    The input may be a pandas DataFrame or any iterable of dict-like rows with
    at least: date, ticker, close. Dates must be ISO-8601 compatible.

    Returns a dict with engine-required metrics:
    - basket_price_above_50dma_pct
    - basket_price_above_200dma_pct
    - basket_ma50_slope_20d
    - chop_score
    - realized_vol_20d_pct
    - vix_pct
    - hyg_lqd_rs_20d
    - spy_tlt_rs_20d
    """
    rows = _coerce_rows(prices)
    series = _group_by_ticker(rows)

    metrics_cfg = cfg.get("metrics", {})
    vix_ticker = str(metrics_cfg.get("vix_ticker", "VIX")).upper()

    required = set(
        str(t).upper()
        for t in metrics_cfg.get(
            "required_tickers", ["SPY", "TLT", "HYG", "LQD", vix_ticker]
        )
    )
    required.add(vix_ticker)

    missing = sorted(required - set(series))
    if missing:
        raise MetricsBuildError(
            "Missing required tickers (required_tickers from config): "
            + ", ".join(missing)
        )

    basket_tickers = [str(t).upper() for t in metrics_cfg.get("basket_tickers", ["SPY"])]
    if not basket_tickers:
        raise MetricsBuildError("basket_tickers must include at least one symbol.")

    missing_basket = sorted(set(basket_tickers) - set(series))
    if missing_basket:
        raise MetricsBuildError(
            f"Missing basket tickers: {', '.join(missing_basket)}"
        )

    as_of_date = _compute_as_of_date(series, required)
    _assert_no_date_gaps(series, required, as_of_date)
    for ticker in basket_tickers:
        dates = {entry[0] for entry in series[ticker]}
        if as_of_date not in dates:
            raise MetricsBuildError(
                f"Missing data for {ticker} on as_of_date {as_of_date}"
            )
    closes_by_ticker = {
        ticker: _slice_series(series[ticker], as_of_date) for ticker in series
    }

    sma_short = int(metrics_cfg.get("sma_short_window", 50))
    sma_long = int(metrics_cfg.get("sma_long_window", 200))
    slope_window = int(metrics_cfg.get("slope_window", 20))
    chop_window = int(metrics_cfg.get("chop_window", 14))
    vol_window = int(metrics_cfg.get("vol_window", 20))
    vol_lookback = int(metrics_cfg.get("vol_lookback", 252))
    vix_lookback = int(metrics_cfg.get("vix_pct_lookback", 252))
    rs_window = int(metrics_cfg.get("rs_window", 20))

    _validate_windows(
        {
            "sma_short_window": sma_short,
            "sma_long_window": sma_long,
            "slope_window": slope_window,
            "chop_window": chop_window,
            "vol_window": vol_window,
            "vol_lookback": vol_lookback,
            "vix_pct_lookback": vix_lookback,
            "rs_window": rs_window,
        }
    )

    basket_above_50 = 0
    basket_above_200 = 0
    slope_values = []
    chop_values = []

    for ticker in basket_tickers:
        closes = closes_by_ticker[ticker]
        _ensure_min_history(closes, sma_short, f"SMA({sma_short})", ticker)
        _ensure_min_history(closes, sma_long, f"SMA({sma_long})", ticker)
        _ensure_min_history(
            closes, sma_short + slope_window, "MA slope", ticker
        )
        _ensure_min_history(closes, chop_window, f"CHOP({chop_window})", ticker)
        close_last = closes[-1]
        sma50 = _simple_moving_average(closes, sma_short)
        sma200 = _simple_moving_average(closes, sma_long)
        if close_last >= sma50:
            basket_above_50 += 1
        if close_last >= sma200:
            basket_above_200 += 1

        slope_values.append(_moving_average_slope(closes, sma_short, slope_window))
        chop_values.append(_chop_score(closes, chop_window))

    basket_price_above_50dma_pct = 100.0 * basket_above_50 / len(basket_tickers)
    basket_price_above_200dma_pct = 100.0 * basket_above_200 / len(basket_tickers)
    basket_ma50_slope_20d = float(sum(slope_values) / len(slope_values))
    chop_score = float(sum(chop_values) / len(chop_values))

    spy_closes = closes_by_ticker["SPY"]
    _ensure_min_history(
        spy_closes, vol_window + vol_lookback, "realized_vol_20d_pct", "SPY"
    )
    realized_vol_20d_pct = _realized_vol_pct(spy_closes, vol_window, vol_lookback)

    vix_closes = closes_by_ticker[vix_ticker]
    _ensure_min_history(vix_closes, vix_lookback, "vix_pct", vix_ticker)
    vix_pct = _percentile_rank(vix_closes[-vix_lookback:], vix_closes[-1])

    required_overlap = rs_window + 1
    overlap_hyg_lqd = _overlap_length(series, ("HYG", "LQD"), as_of_date)
    if overlap_hyg_lqd < required_overlap:
        raise MetricsBuildError(
            "Insufficient overlap for hyg_lqd_rs_20d "
            f"(lookback {rs_window}): have {overlap_hyg_lqd}, "
            f"need {required_overlap}."
        )
    overlap_spy_tlt = _overlap_length(series, ("SPY", "TLT"), as_of_date)
    if overlap_spy_tlt < required_overlap:
        raise MetricsBuildError(
            "Insufficient overlap for spy_tlt_rs_20d "
            f"(lookback {rs_window}): have {overlap_spy_tlt}, "
            f"need {required_overlap}."
        )
    hyg_lqd_rs_20d = _relative_strength(
        closes_by_ticker["HYG"], closes_by_ticker["LQD"], rs_window
    )
    spy_tlt_rs_20d = _relative_strength(
        closes_by_ticker["SPY"], closes_by_ticker["TLT"], rs_window
    )

    metrics = {
        "basket_price_above_50dma_pct": float(basket_price_above_50dma_pct),
        "basket_price_above_200dma_pct": float(basket_price_above_200dma_pct),
        "basket_ma50_slope_20d": float(basket_ma50_slope_20d),
        "chop_score": float(chop_score),
        "realized_vol_20d_pct": float(realized_vol_20d_pct),
        "vix_pct": float(vix_pct),
        "hyg_lqd_rs_20d": float(hyg_lqd_rs_20d),
        "spy_tlt_rs_20d": float(spy_tlt_rs_20d),
    }

    for key, value in metrics.items():
        if not _is_finite(value):
            raise MetricsBuildError(f"Non-finite metric computed: {key}={value}")

    return metrics


def _coerce_rows(prices: Any) -> List[Mapping[str, Any]]:
    if prices is None:
        raise MetricsBuildError("prices input is required.")

    try:
        import pandas as pd  # type: ignore
    except Exception:
        pd = None

    if pd is not None and hasattr(pd, "DataFrame") and isinstance(prices, pd.DataFrame):
        return prices.to_dict("records")

    if isinstance(prices, list):
        return prices

    if isinstance(prices, dict):
        keys = list(prices.keys())
        lengths = {len(prices[key]) for key in keys if isinstance(prices[key], list)}
        if len(lengths) != 1:
            raise MetricsBuildError("Column-based prices input has uneven lengths.")
        count = lengths.pop() if lengths else 0
        rows = []
        for idx in range(count):
            row = {key: prices[key][idx] for key in keys}
            rows.append(row)
        return rows

    raise MetricsBuildError("Unsupported prices input type.")


def _group_by_ticker(
    rows: Iterable[Mapping[str, Any]],
) -> Dict[str, List[Tuple[date, float]]]:
    grouped: Dict[str, Dict[date, float]] = {}
    for row in rows:
        if not {"date", "ticker", "close"}.issubset(row):
            raise MetricsBuildError("Each row must include date, ticker, close.")

        ticker = str(row["ticker"]).upper().strip()
        if not ticker:
            raise MetricsBuildError("Ticker cannot be empty.")

        row_date = _parse_date(row["date"])
        close = _parse_float(row["close"], "close")
        grouped.setdefault(ticker, {})
        if row_date in grouped[ticker]:
            raise MetricsBuildError(f"Duplicate date for {ticker}: {row_date}")
        grouped[ticker][row_date] = close

    series: Dict[str, List[Tuple[date, float]]] = {}
    for ticker, values in grouped.items():
        ordered = sorted(values.items(), key=lambda item: item[0])
        series[ticker] = ordered

    if not series:
        raise MetricsBuildError("No price rows provided.")

    return series


def _assert_no_date_gaps(
    series: Dict[str, List[Tuple[date, float]]],
    tickers: Iterable[str],
    as_of_date: date,
) -> None:
    allowed_gaps = {1, 2, 3}
    for ticker in tickers:
        dates = [row_date for row_date, _ in series[ticker] if row_date <= as_of_date]
        for prev, curr in zip(dates, dates[1:]):
            gap_days = (curr - prev).days
            if gap_days not in allowed_gaps:
                raise MetricsBuildError(
                    f"Missing days for {ticker}: {prev} -> {curr} "
                    f"(gap {gap_days} days)."
                )


def _overlap_length(
    series: Dict[str, List[Tuple[date, float]]],
    tickers: Iterable[str],
    as_of_date: date,
) -> int:
    date_sets = []
    for ticker in tickers:
        date_sets.append(
            {row_date for row_date, _ in series[ticker] if row_date <= as_of_date}
        )
    if not date_sets:
        return 0
    return len(set.intersection(*date_sets))


def _ensure_min_history(
    series: Sequence[float], required_len: int, metric: str, ticker: str
) -> None:
    if len(series) < required_len:
        raise MetricsBuildError(
            f"Insufficient history for {metric} on {ticker}; "
            f"need {required_len}, have {len(series)}."
        )


def _compute_as_of_date(
    series: Dict[str, List[Tuple[date, float]]], required: set[str]
) -> date:
    latest_dates: List[date] = []
    for ticker in required:
        dates = [entry[0] for entry in series[ticker]]
        if not dates:
            raise MetricsBuildError(f"No dates found for {ticker}.")
        latest_dates.append(max(dates))

    as_of_date = min(latest_dates)
    for ticker in required:
        dates = {entry[0] for entry in series[ticker]}
        if as_of_date not in dates:
            raise MetricsBuildError(
                f"Missing data for {ticker} on as_of_date {as_of_date}"
            )

    return as_of_date


def _slice_series(series: List[Tuple[date, float]], as_of: date) -> List[float]:
    values = [close for row_date, close in series if row_date <= as_of]
    if not values:
        raise MetricsBuildError("No prices available at or before as_of_date.")
    return values


def _parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1]
        try:
            return datetime.fromisoformat(text).date()
        except ValueError as exc:
            raise MetricsBuildError(f"Invalid date value: {value}") from exc
    raise MetricsBuildError(f"Invalid date value: {value}")


def _parse_float(value: Any, field: str) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError) as exc:
        raise MetricsBuildError(f"Invalid numeric {field}: {value}") from exc
    if not _is_finite(num):
        raise MetricsBuildError(f"Invalid numeric {field}: {value}")
    return num


def _is_finite(value: float) -> bool:
    return math.isfinite(value)


def _validate_windows(windows: Dict[str, int]) -> None:
    for key, value in windows.items():
        if value <= 0:
            raise MetricsBuildError(f"Window {key} must be positive.")


def _simple_moving_average(series: Sequence[float], window: int) -> float:
    if len(series) < window:
        raise MetricsBuildError(
            f"Insufficient history for SMA({window}); have {len(series)} points."
        )
    return float(sum(series[-window:]) / window)


def _moving_average_slope(series: Sequence[float], window: int, slope_window: int) -> float:
    if len(series) < window + slope_window:
        raise MetricsBuildError(
            f"Insufficient history for MA slope; need {window + slope_window} points."
        )

    ma_values = _sma_series(series, window)
    if len(ma_values) <= slope_window:
        raise MetricsBuildError("Insufficient MA history for slope computation.")

    recent = ma_values[-1]
    previous = ma_values[-1 - slope_window]
    if previous == 0:
        raise MetricsBuildError("MA slope reference is zero.")
    return float((recent / previous - 1.0) * 100.0)


def _sma_series(series: Sequence[float], window: int) -> List[float]:
    if len(series) < window:
        raise MetricsBuildError(
            f"Insufficient history for SMA series; need {window} points."
        )
    values = []
    running = sum(series[:window])
    values.append(running / window)
    for idx in range(window, len(series)):
        running += series[idx] - series[idx - window]
        values.append(running / window)
    return values


def _chop_score(series: Sequence[float], window: int) -> float:
    if len(series) < window:
        raise MetricsBuildError(
            f"Insufficient history for CHOP({window}); have {len(series)} points."
        )
    window_series = series[-window:]
    diffs = [
        abs(window_series[i] - window_series[i - 1])
        for i in range(1, len(window_series))
    ]
    sum_tr = sum(diffs)
    max_close = max(window_series)
    min_close = min(window_series)
    if max_close == min_close:
        return 100.0
    ratio = sum_tr / (max_close - min_close)
    if ratio <= 0:
        return 0.0
    chop = 100.0 * math.log10(ratio) / math.log10(window)
    return float(_clamp(chop, 0.0, 100.0))


def _realized_vol_pct(series: Sequence[float], window: int, lookback: int) -> float:
    if len(series) <= window:
        raise MetricsBuildError("Insufficient history for realized volatility.")
    returns = _log_returns(series)
    vol_series = _rolling_realized_vol(returns, window)
    if len(vol_series) < lookback:
        raise MetricsBuildError(
            f"Insufficient history for realized vol percentile; need {lookback}."
        )
    window_series = vol_series[-lookback:]
    return float(_percentile_rank(window_series, window_series[-1]))


def _log_returns(series: Sequence[float]) -> List[float]:
    returns = []
    for idx in range(1, len(series)):
        prev = series[idx - 1]
        current = series[idx]
        if prev <= 0 or current <= 0:
            raise MetricsBuildError("Prices must be positive for log returns.")
        returns.append(math.log(current / prev))
    return returns


def _rolling_realized_vol(returns: Sequence[float], window: int) -> List[float]:
    if len(returns) < window:
        raise MetricsBuildError("Insufficient history for realized vol series.")
    vols = []
    for idx in range(window, len(returns) + 1):
        window_slice = returns[idx - window : idx]
        mean = sum(window_slice) / window
        variance = sum((val - mean) ** 2 for val in window_slice) / window
        vol = math.sqrt(variance) * math.sqrt(252.0) * 100.0
        vols.append(vol)
    return vols


def _percentile_rank(values: Sequence[float], value: float) -> float:
    if not values:
        raise MetricsBuildError("Empty series for percentile computation.")
    if len(values) == 1:
        return 0.0
    sorted_vals = sorted(values)
    count_le = 0
    for val in sorted_vals:
        if val <= value:
            count_le += 1
    return 100.0 * (count_le - 1) / (len(sorted_vals) - 1)


def _relative_strength(series_a: Sequence[float], series_b: Sequence[float], window: int) -> float:
    if len(series_a) <= window or len(series_b) <= window:
        raise MetricsBuildError("Insufficient history for relative strength.")
    pct_a = _percent_change(series_a, window)
    pct_b = _percent_change(series_b, window)
    return float(pct_a - pct_b)


def _percent_change(series: Sequence[float], window: int) -> float:
    if len(series) <= window:
        raise MetricsBuildError("Insufficient history for percent change.")
    start = series[-1 - window]
    end = series[-1]
    if start == 0:
        raise MetricsBuildError("Percent change reference is zero.")
    return float((end / start - 1.0) * 100.0)


def _clamp(value: float, low: float, high: float) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value
