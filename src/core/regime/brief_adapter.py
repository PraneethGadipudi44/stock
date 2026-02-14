from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


ADAPTER_VERSION = "brief_adapter_v1"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

CLOSE_DP = Decimal("0.01")
PCT_DP = Decimal("0.000001")  # 6dp
SCORE_DP = Decimal("0.0001")  # 4dp

RECENT_DAYS = 5
FOCUS_LIST_SIZE = 10


class BriefError(Exception):
    pass


class BriefNoDataError(Exception):
    pass


@dataclass(frozen=True)
class CachePaths:
    brief: Path
    meta: Path
    markdown: Path


def sha256_hex(data: bytes) -> str:
    return sha256(data).hexdigest()


def inputs_hash(as_of: str, prices_hash: str, filings_hash: str, catalysts_hash: str) -> str:
    payload = (
        f"{as_of}\n{prices_hash}\n{filings_hash}\n{catalysts_hash}\n".encode("utf-8")
    )
    return sha256_hex(payload)


def cache_paths(cache_dir: Path, inputs_digest: str) -> CachePaths:
    base = cache_dir / "v1" / inputs_digest
    return CachePaths(
        brief=base / "brief.json",
        meta=base / "brief.meta.json",
        markdown=base / "brief.md",
    )


def _require_keys(payload: Dict[str, Any], keys: Iterable[str], label: str) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise BriefError(f"Missing {label} keys: {', '.join(missing)}")


def load_prices_meta(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BriefError("Prices meta is not valid JSON.") from exc
    _require_keys(
        payload,
        ["source_hash", "normalized_csv_hash", "request_canonical", "cache_key"],
        "prices_meta",
    )
    return payload


def load_filings_meta(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BriefError("Filings meta is not valid JSON.") from exc
    _require_keys(
        payload,
        ["source_hash", "normalized_jsonl_hash", "request_canonical", "cache_key"],
        "filings_meta",
    )
    return payload


def load_catalysts_meta(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BriefError("Catalysts meta is not valid JSON.") from exc
    _require_keys(
        payload,
        ["normalized_jsonl_hash", "inputs_hash"],
        "catalysts_meta",
    )
    return payload


def _to_decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except Exception as exc:  # pragma: no cover
        raise BriefError("Invalid decimal value.") from exc


def load_prices(path: Path) -> Tuple[Dict[str, Dict[str, Decimal]], Dict[str, List[str]], List[str], int]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["date", "ticker", "close"]:
            raise BriefError("Prices CSV header must be date,ticker,close.")
        prices: Dict[str, Dict[str, Decimal]] = {}
        dates: Dict[str, List[str]] = {}
        rows = 0
        all_dates: set[str] = set()
        for row in reader:
            date = row.get("date", "")
            ticker = row.get("ticker", "").upper()
            close_text = row.get("close", "")
            if not DATE_RE.match(date):
                raise BriefError("Invalid date in prices CSV.")
            if not ticker:
                raise BriefError("Missing ticker in prices CSV.")
            close = _to_decimal(close_text).quantize(CLOSE_DP, rounding=ROUND_HALF_UP)
            prices.setdefault(ticker, {})[date] = close
            dates.setdefault(ticker, []).append(date)
            all_dates.add(date)
            rows += 1
        for ticker in dates:
            dates[ticker] = sorted(set(dates[ticker]))
        global_dates = sorted(all_dates)
        return prices, dates, global_dates, rows


def load_catalysts(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BriefError("Catalysts JSONL contains invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise BriefError("Catalysts JSONL record must be object.")
        _require_keys(
            payload,
            [
                "ticker",
                "event_date",
                "event_type",
                "form",
                "filing_date",
                "acceptance_datetime",
                "accession_number",
                "url_filing_detail",
            ],
            "catalyst_record",
        )
        records.append(payload)
    return records


def load_filings_tickers(path: Path) -> Tuple[int, List[str]]:
    tickers: set[str] = set()
    rows = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BriefError("Filings JSONL contains invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise BriefError("Filings JSONL record must be object.")
        ticker = str(payload.get("ticker", "")).upper()
        if ticker:
            tickers.add(ticker)
        rows += 1
    return rows, sorted(tickers)


def _round_decimal(value: Decimal, quant: Decimal) -> Decimal:
    return value.quantize(quant, rounding=ROUND_HALF_UP)


def _pct_change(curr: Decimal, prev: Decimal) -> Decimal:
    if prev == 0:
        return Decimal("0")
    return (curr / prev) - Decimal("1")


def _format_pct_reason(pct: Optional[Decimal]) -> str:
    if pct is None:
        return "1d move: n/a"
    pct_val = _round_decimal(pct * Decimal("100"), Decimal("0.01"))
    sign = "+" if pct_val >= 0 else ""
    return f"1d move: {sign}{pct_val:.2f}%"


def _score_value(pct_1d: Optional[Decimal], has_today: bool, has_recent: bool) -> Decimal:
    base = abs(pct_1d) * Decimal("100") if pct_1d is not None else Decimal("0")
    bonus = Decimal("0")
    if has_today:
        bonus += Decimal("10")
    if has_recent:
        bonus += Decimal("5")
    return _round_decimal(base + bonus, SCORE_DP)


def build_brief(
    *,
    as_of: str,
    prices: Dict[str, Dict[str, Decimal]],
    dates: Dict[str, List[str]],
    global_dates: List[str],
    catalysts: List[Dict[str, Any]],
    filings_rows: int,
    filings_tickers: List[str],
    prices_rows: int,
) -> Tuple[Dict[str, Any], Dict[str, int]]:
    if not DATE_RE.match(as_of):
        raise BriefError("Invalid as_of date.")

    as_of_has_prices = as_of in global_dates
    if not as_of_has_prices:
        raise BriefNoDataError("No prices available for as_of date.")

    recent_dates: List[str] = []
    if as_of in global_dates:
        idx = global_dates.index(as_of)
        start = max(0, idx - RECENT_DAYS)
        recent_dates = global_dates[start:idx]

    catalysts_today = []
    catalysts_recent = []
    for record in catalysts:
        event_date = record.get("event_date")
        if event_date == as_of:
            catalysts_today.append(record)
        elif event_date in recent_dates:
            catalysts_recent.append(record)

    catalysts_today.sort(
        key=lambda item: (
            item.get("ticker", ""),
            item.get("event_date", ""),
            item.get("form", ""),
            item.get("accession_number", ""),
        )
    )
    catalysts_recent.sort(
        key=lambda item: (
            item.get("ticker", ""),
            item.get("event_date", ""),
            item.get("form", ""),
            item.get("accession_number", ""),
        )
    )

    price_moves = []
    focus_candidates = []
    tickers_in_prices = sorted(prices.keys())

    for ticker in tickers_in_prices:
        if as_of not in prices[ticker]:
            continue
        close = prices[ticker][as_of]
        ticker_dates = dates[ticker]
        idx = ticker_dates.index(as_of)
        pct_1d: Optional[Decimal] = None
        pct_5d: Optional[Decimal] = None
        if idx >= 1:
            prev = prices[ticker][ticker_dates[idx - 1]]
            pct_1d = _round_decimal(_pct_change(close, prev), PCT_DP)
        if idx >= 5:
            prev5 = prices[ticker][ticker_dates[idx - 5]]
            pct_5d = _round_decimal(_pct_change(close, prev5), PCT_DP)

        price_moves.append(
            {
                "ticker": ticker,
                "close": float(close),
                "pct_1d": float(pct_1d) if pct_1d is not None else None,
                "pct_5d": float(pct_5d) if pct_5d is not None else None,
            }
        )

        ticker_today = [c for c in catalysts_today if c.get("ticker") == ticker]
        ticker_recent = [c for c in catalysts_recent if c.get("ticker") == ticker]
        has_today = bool(ticker_today)
        has_recent = bool(ticker_recent)

        score = _score_value(pct_1d, has_today, has_recent)

        reasons = [_format_pct_reason(pct_1d)]
        if ticker_today:
            reasons.append(f"Catalyst today: {ticker_today[0].get('form')}")
        if ticker_recent:
            reasons.append(f"Recent catalyst: {ticker_recent[0].get('form')}")
        if len(reasons) < 2:
            reasons.append("No catalyst in last 5 days")
        if len(reasons) > 5:
            reasons = reasons[:5]

        focus_candidates.append(
            {
                "ticker": ticker,
                "score": float(score),
                "reasons": reasons,
                "has_catalyst_today": has_today,
                "has_recent_catalyst": has_recent,
            }
        )

    price_moves.sort(key=lambda item: item["ticker"])
    focus_candidates.sort(key=lambda item: (-item["score"], item["ticker"]))
    focus_list = focus_candidates[:FOCUS_LIST_SIZE]

    brief = {
        "schema_version": 1,
        "as_of": as_of,
        "focus_list": focus_list,
        "today_catalysts": [
            {
                "ticker": item.get("ticker"),
                "event_date": item.get("event_date"),
                "event_type": item.get("event_type"),
                "form": item.get("form"),
                "filing_date": item.get("filing_date"),
                "acceptance_datetime": item.get("acceptance_datetime"),
                "accession_number": item.get("accession_number"),
                "url_filing_detail": item.get("url_filing_detail"),
            }
            for item in catalysts_today
        ],
        "recent_catalysts": [
            {
                "ticker": item.get("ticker"),
                "event_date": item.get("event_date"),
                "event_type": item.get("event_type"),
                "form": item.get("form"),
                "filing_date": item.get("filing_date"),
                "acceptance_datetime": item.get("acceptance_datetime"),
                "accession_number": item.get("accession_number"),
                "url_filing_detail": item.get("url_filing_detail"),
            }
            for item in catalysts_recent
        ],
        "price_moves": price_moves,
        "data_coverage": {
            "prices_rows": int(prices_rows),
            "filings_rows": filings_rows,
            "catalysts_rows": len(catalysts),
            "tickers_in_prices": tickers_in_prices,
            "tickers_in_filings": filings_tickers,
            "tickers_in_catalysts": sorted({c.get("ticker", "") for c in catalysts}),
            "as_of_has_prices": bool(as_of_has_prices),
        },
    }
    rows_meta = {
        "focus_list": len(focus_list),
        "today_catalysts": len(catalysts_today),
        "recent_catalysts": len(catalysts_recent),
        "price_moves": len(price_moves),
    }
    return brief, rows_meta


def render_markdown(brief: Dict[str, Any]) -> str:
    lines = [f"# Morning Brief ({brief['as_of']})", ""]
    lines.append("## Focus List")
    for item in brief["focus_list"]:
        reasons = "; ".join(item["reasons"])
        lines.append(f"- {item['ticker']}: score={item['score']:.4f} ({reasons})")
    lines.append("")
    lines.append("## Today Catalysts")
    for item in brief["today_catalysts"]:
        lines.append(
            f"- {item['ticker']} {item['form']} {item['event_date']} {item['accession_number']}"
        )
    lines.append("")
    lines.append("## Recent Catalysts")
    for item in brief["recent_catalysts"]:
        lines.append(
            f"- {item['ticker']} {item['form']} {item['event_date']} {item['accession_number']}"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def build_meta(
    *,
    prices_meta: Dict[str, Any],
    filings_meta: Dict[str, Any],
    catalysts_meta: Dict[str, Any],
    inputs_digest: str,
    brief_hash: str,
    markdown_hash: Optional[str],
    rows: Dict[str, int],
    cache_hit: bool,
) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "adapter_version": ADAPTER_VERSION,
        "inputs": {
            "prices": {
                "source_hash": prices_meta["source_hash"],
                "normalized_csv_hash": prices_meta["normalized_csv_hash"],
                "request_canonical": prices_meta["request_canonical"],
                "cache_key": prices_meta["cache_key"],
            },
            "filings": {
                "source_hash": filings_meta["source_hash"],
                "normalized_jsonl_hash": filings_meta["normalized_jsonl_hash"],
                "request_canonical": filings_meta["request_canonical"],
                "cache_key": filings_meta["cache_key"],
            },
            "catalysts": {
                "normalized_jsonl_hash": catalysts_meta["normalized_jsonl_hash"],
                "inputs_hash": catalysts_meta["inputs_hash"],
            },
        },
        "inputs_hash": inputs_digest,
        "normalized_brief_hash": brief_hash,
        "markdown_hash": markdown_hash,
        "rows": rows,
        "cache_hit": bool(cache_hit),
    }
