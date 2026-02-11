from __future__ import annotations

import pytest

from core.regime.prices_io import PricesIOError, read_prices_csv_text


def test_read_prices_csv_text_parses_rows():
    text = "date,ticker,close\n2026-01-01,SPY,100\n2026-01-01,TLT,90\n"
    rows = read_prices_csv_text(text)
    assert len(rows) == 2
    assert rows[0].ticker == "SPY"


def test_read_prices_csv_text_missing_headers():
    with pytest.raises(PricesIOError):
        read_prices_csv_text("date,ticker\n2026-01-01,SPY\n")


def test_read_prices_csv_text_duplicate_rows():
    text = (
        "date,ticker,close\n"
        "2026-01-01,SPY,100\n"
        "2026-01-01,SPY,100\n"
    )
    with pytest.raises(PricesIOError, match="Duplicate row"):
        read_prices_csv_text(text)


def test_read_prices_csv_text_out_of_order():
    text = (
        "date,ticker,close\n"
        "2026-01-02,SPY,100\n"
        "2026-01-01,SPY,101\n"
    )
    with pytest.raises(PricesIOError, match="Out-of-order date"):
        read_prices_csv_text(text)
