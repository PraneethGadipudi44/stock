from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


ADAPTER_VERSION = "catalysts_adapter_v1"


class CatalystError(Exception):
    pass


class CatalystNoDataError(Exception):
    pass


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
URL_RE = re.compile(r"^https://www\.sec\.gov/Archives/edgar/data/")


@dataclass(frozen=True)
class CachePaths:
    jsonl: Path
    meta: Path


def sha256_hex(data: bytes) -> str:
    return sha256(data).hexdigest()


def inputs_hash(prices_hash: str, filings_hash: str) -> str:
    payload = f"{prices_hash}\n{filings_hash}\n".encode("utf-8")
    return sha256_hex(payload)


def cache_paths(cache_dir: Path, inputs_digest: str) -> CachePaths:
    base = cache_dir / "v1" / inputs_digest
    return CachePaths(
        jsonl=base / "catalysts.jsonl",
        meta=base / "catalysts.meta.json",
    )


def _require_keys(payload: Dict[str, Any], keys: Iterable[str], label: str) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise CatalystError(f"Missing {label} keys: {', '.join(missing)}")


def load_prices_meta(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CatalystError("Prices meta is not valid JSON.") from exc

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
        raise CatalystError("Filings meta is not valid JSON.") from exc

    _require_keys(
        payload,
        ["source_hash", "normalized_jsonl_hash", "request_canonical", "cache_key"],
        "filings_meta",
    )
    return payload


def load_prices_dates(path: Path) -> Dict[str, set[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["date", "ticker", "close"]:
            raise CatalystError("Prices CSV header must be date,ticker,close.")
        dates: Dict[str, set[str]] = {}
        for row in reader:
            date = row.get("date", "")
            ticker = row.get("ticker", "").upper()
            if not DATE_RE.match(date):
                raise CatalystError("Invalid date in prices CSV.")
            if not ticker:
                raise CatalystError("Missing ticker in prices CSV.")
            dates.setdefault(ticker, set()).add(date)
    return dates


def _validate_filing_record(record: Dict[str, Any]) -> None:
    required = [
        "acceptance_datetime",
        "accession_number",
        "cik",
        "filing_date",
        "form",
        "primary_doc",
        "ticker",
        "url_filing_detail",
    ]
    _require_keys(record, required, "filing_record")

    if record["acceptance_datetime"] is not None and not isinstance(
        record["acceptance_datetime"], str
    ):
        raise CatalystError("Invalid acceptance_datetime in filings JSONL.")
    if record["acceptance_datetime"]:
        if not record["acceptance_datetime"].endswith("Z"):
            raise CatalystError("acceptance_datetime must end with Z.")
    if not DATE_RE.match(record["filing_date"]):
        raise CatalystError("Invalid filing_date in filings JSONL.")
    if not URL_RE.match(record["url_filing_detail"]):
        raise CatalystError("Invalid url_filing_detail in filings JSONL.")


def load_filings(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CatalystError("Filings JSONL contains invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise CatalystError("Filings JSONL record must be object.")
        _validate_filing_record(payload)
        records.append(payload)
    return records


def build_catalysts(
    filings: List[Dict[str, Any]],
    price_dates: Dict[str, set[str]],
) -> Tuple[str, int]:
    if not filings:
        raise CatalystNoDataError("No filings available for join.")

    records: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str, str]] = set()

    for record in filings:
        ticker = str(record["ticker"]).upper()
        filing_date = record["filing_date"]
        accession = record["accession_number"]
        key = (ticker, filing_date, accession)
        if key in seen:
            raise CatalystError("Duplicate catalyst record detected.")
        seen.add(key)
        has_price = filing_date in price_dates.get(ticker, set())
        records.append(
            {
                "schema_version": 1,
                "ticker": ticker,
                "event_date": filing_date,
                "event_type": "sec_filing",
                "form": record["form"],
                "filing_date": filing_date,
                "acceptance_datetime": record["acceptance_datetime"],
                "accession_number": accession,
                "url_filing_detail": record["url_filing_detail"],
                "has_price_row": bool(has_price),
            }
        )

    records.sort(
        key=lambda item: (
            item["ticker"],
            item["event_date"],
            item["form"],
            item["accession_number"],
        )
    )
    lines = [json.dumps(record, sort_keys=True) for record in records]
    return "\n".join(lines) + "\n", len(records)


def build_meta(
    *,
    prices_meta: Dict[str, Any],
    filings_meta: Dict[str, Any],
    inputs_digest: str,
    jsonl_hash: str,
    rows: int,
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
        },
        "inputs_hash": inputs_digest,
        "normalized_jsonl_hash": jsonl_hash,
        "rows": int(rows),
        "cache_hit": bool(cache_hit),
    }
