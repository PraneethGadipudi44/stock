from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


POLYGON_BASE_URL = "https://api.polygon.io"
PROVIDER = "polygon"
PROVIDER_VERSION = "v2"
ADAPTER_VERSION = "prices_adapter_v1"
DATE_SEMANTICS = "end_inclusive"
ROUNDING_MODE = "HALF_UP"

QUERY_PARAMS = [
    ("adjusted", "true"),
    ("sort", "asc"),
    ("limit", "50000"),
]


class ProviderResponseError(Exception):
    pass


class NoDataError(Exception):
    pass


@dataclass(frozen=True)
class RequestSpec:
    path: str
    query: str
    canonical: str
    fingerprint: str


@dataclass(frozen=True)
class CachePaths:
    raw: Path
    csv: Path
    meta: Path
    cache_key: str
    request_canonical: str
    endpoint: str


def _canonical_query() -> str:
    return "&".join(f"{key}={value}" for key, value in QUERY_PARAMS)


def _request_spec(symbol: str, start: str, end: str) -> RequestSpec:
    path = f"/v2/aggs/ticker/{symbol}/range/1/day/{start}/{end}"
    query = _canonical_query()
    canonical = f"{path}?{query}"
    fingerprint = sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return RequestSpec(path=path, query=query, canonical=canonical, fingerprint=fingerprint)


def cache_paths(cache_dir: Path, symbol: str, start: str, end: str) -> CachePaths:
    symbol = symbol.upper()
    spec = _request_spec(symbol, start, end)
    base = cache_dir / PROVIDER / symbol
    stem = f"{start}_{end}_{spec.fingerprint}"
    return CachePaths(
        raw=base / f"{stem}.json",
        csv=base / f"{stem}.csv",
        meta=base / f"{stem}.meta.json",
        cache_key=spec.fingerprint,
        request_canonical=spec.canonical,
        endpoint=spec.path,
    )


def fetch_polygon_raw(symbol: str, start: str, end: str, api_key: str) -> bytes:
    spec = _request_spec(symbol, start, end)
    url = f"{POLYGON_BASE_URL}{spec.path}?{spec.query}&apiKey={api_key}"
    request = Request(url, headers={"User-Agent": "eds-regime/1.0"})
    try:
        with urlopen(request, timeout=30) as response:
            return response.read()
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise ProviderResponseError("Provider auth error (HTTP 401/403).") from exc
        if exc.code == 429:
            raise ProviderResponseError("Provider rate limit (HTTP 429).") from exc
        if 500 <= exc.code:
            raise ProviderResponseError("Provider unavailable (HTTP 5xx).") from exc
        raise ProviderResponseError(f"Provider error (HTTP {exc.code}).") from exc
    except URLError as exc:
        raise ProviderResponseError("Provider unavailable (network error).") from exc


def _parse_results(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if "results" not in payload:
        raise ProviderResponseError("Provider schema drift: missing results.")
    results = payload["results"]
    if not isinstance(results, list):
        raise ProviderResponseError("Provider schema drift: results is not a list.")
    if not results:
        raise NoDataError("No data returned by provider.")
    return results


def _format_close(value: Any) -> str:
    try:
        dec = Decimal(str(value)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    except Exception as exc:  # pragma: no cover - defensive
        raise ProviderResponseError("Provider schema drift: invalid close.") from exc
    return f"{dec:.2f}"


def _to_iso_date(epoch_ms: Any) -> str:
    try:
        ts = float(epoch_ms) / 1000.0
    except Exception as exc:
        raise ProviderResponseError("Provider schema drift: invalid timestamp.") from exc
    return datetime.fromtimestamp(ts, timezone.utc).date().isoformat()


def normalize_polygon_raw(raw: bytes, symbol: str) -> Tuple[str, int]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderResponseError("Provider response is not valid JSON.") from exc

    results = _parse_results(payload)
    rows: List[Tuple[str, str]] = []
    for item in results:
        if not isinstance(item, dict):
            raise ProviderResponseError("Provider schema drift: result is not object.")
        if "t" not in item or "c" not in item:
            raise ProviderResponseError("Provider schema drift: missing fields in result.")
        date = _to_iso_date(item["t"])
        close = _format_close(item["c"])
        rows.append((date, close))

    rows.sort(key=lambda item: item[0])
    seen: set[str] = set()
    for date, _ in rows:
        if date in seen:
            raise ProviderResponseError("Provider schema drift: duplicate dates.")
        seen.add(date)

    header = "date,ticker,close"
    lines = [header]
    ticker = symbol.upper()
    for date, close in rows:
        lines.append(f"{date},{ticker},{close}")
    csv_text = "\n".join(lines) + "\n"
    return csv_text, len(rows)


def build_meta(
    *,
    symbol: str,
    start: str,
    end: str,
    request_canonical: str,
    cache_key: str,
    endpoint: str,
    raw_hash: str,
    csv_hash: str,
    rows: int,
    cache_hit: bool,
) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "provider": PROVIDER,
        "provider_version": PROVIDER_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "endpoint": endpoint,
        "request_canonical": request_canonical,
        "cache_key": cache_key,
        "symbol": symbol.upper(),
        "start": start,
        "end": end,
        "date_semantics": DATE_SEMANTICS,
        "rounding_mode": ROUNDING_MODE,
        "rows": int(rows),
        "source_hash": raw_hash,
        "normalized_csv_hash": csv_hash,
        "cache_hit": bool(cache_hit),
    }


def sha256_hex(data: bytes) -> str:
    return sha256(data).hexdigest()
