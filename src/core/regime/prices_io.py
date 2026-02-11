from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, List, Mapping, Optional, Protocol


class PricesIOError(ValueError):
    """Raised when price input data cannot be parsed."""


@dataclass(frozen=True)
class PriceRow:
    date: date
    ticker: str
    close: float


class PriceProvider(Protocol):
    """Interface for price providers."""

    def fetch_prices(self, *args: Any, **kwargs: Any) -> List[PriceRow]:
        raise NotImplementedError


class CsvPriceProvider:
    """CSV-only price provider for offline-first workflows."""

    def __init__(self, path: str) -> None:
        self.path = path

    def fetch_prices(self, *_: Any, **__: Any) -> List[PriceRow]:
        return read_prices_csv(self.path)


def read_prices_csv(path: str) -> List[PriceRow]:
    """Read a long-format CSV (date,ticker,close)."""
    with open(path, "r", encoding="utf-8") as handle:
        return read_prices_csv_text(handle.read())


def read_prices_csv_text(text: str) -> List[PriceRow]:
    """Parse CSV text into PriceRow entries."""
    if not text.strip():
        raise PricesIOError("Prices CSV is empty.")

    reader = csv.DictReader(text.splitlines())
    if reader.fieldnames is None:
        raise PricesIOError("Prices CSV is missing headers.")

    header_map = {name.lower(): name for name in reader.fieldnames}
    headers = set(header_map.keys())
    if not {"date", "ticker", "close"}.issubset(headers):
        raise PricesIOError("Prices CSV must include date,ticker,close columns.")

    rows: List[PriceRow] = []
    seen: set[tuple[str, date]] = set()
    last_date_by_ticker: dict[str, date] = {}
    for row in reader:
        row_date = _parse_date(row[header_map["date"]])
        ticker = str(row[header_map["ticker"]]).upper().strip()
        if not ticker:
            raise PricesIOError("Ticker cannot be empty.")
        last_date = last_date_by_ticker.get(ticker)
        if last_date is not None and row_date < last_date:
            raise PricesIOError(
                f"Out-of-order date for {ticker}: {last_date} -> {row_date}."
            )
        key = (ticker, row_date)
        if key in seen:
            raise PricesIOError(f"Duplicate row for {ticker} on {row_date}.")
        close = _parse_float(row[header_map["close"]], "close")
        rows.append(PriceRow(date=row_date, ticker=ticker, close=close))
        seen.add(key)
        last_date_by_ticker[ticker] = row_date

    if not rows:
        raise PricesIOError("Prices CSV contains no rows.")

    return rows


def rows_to_records(rows: Iterable[PriceRow]) -> List[Mapping[str, Any]]:
    """Convert PriceRow entries into dict records for metrics builder."""
    return [
        {"date": row.date, "ticker": row.ticker, "close": row.close}
        for row in rows
    ]


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
            raise PricesIOError(f"Invalid date value: {value}") from exc
    raise PricesIOError(f"Invalid date value: {value}")


def _parse_float(value: Any, field: str) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError) as exc:
        raise PricesIOError(f"Invalid numeric {field}: {value}") from exc
    if not (num == num and num not in (float("inf"), float("-inf"))):
        raise PricesIOError(f"Invalid numeric {field}: {value}")
    return num
