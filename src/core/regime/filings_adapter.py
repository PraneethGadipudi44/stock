from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SEC_BASE_URL = "https://www.sec.gov"
SEC_DATA_URL = "https://data.sec.gov"
PROVIDER = "edgar"
PROVIDER_VERSION = "submissions+archives_v1"
ADAPTER_VERSION = "filings_adapter_v1"
DATE_SEMANTICS = "end_inclusive"
FORMS = ["10-K", "10-Q", "8-K"]
TICKERS_FILENAME = "company_tickers.json"


class ProviderResponseError(Exception):
    pass


class NoDataError(Exception):
    pass


@dataclass(frozen=True)
class RequestSpec:
    tickers_path: str
    submissions_path: str
    canonical: str
    fingerprint: str


@dataclass(frozen=True)
class CachePaths:
    raw: Path
    jsonl: Path
    meta: Path
    cache_key: str
    request_canonical: str
    endpoint: str


def sha256_hex(data: bytes) -> str:
    return sha256(data).hexdigest()


def _canonical_request(
    ticker: str, cik_padded: str, start: str, end: str
) -> RequestSpec:
    tickers_path = "/files/company_tickers.json"
    submissions_path = f"/submissions/CIK{cik_padded}.json"
    forms = ",".join(FORMS)
    canonical = (
        f"provider={PROVIDER}&ticker={ticker}&cik={cik_padded}"
        f"&start={start}&end={end}&forms={forms}"
        f"&tickers_endpoint={tickers_path}&submissions_endpoint={submissions_path}"
    )
    fingerprint = sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return RequestSpec(
        tickers_path=tickers_path,
        submissions_path=submissions_path,
        canonical=canonical,
        fingerprint=fingerprint,
    )


def cache_paths(
    cache_dir: Path, ticker: str, start: str, end: str, cik_padded: str
) -> CachePaths:
    spec = _canonical_request(ticker, cik_padded, start, end)
    base = cache_dir / PROVIDER / ticker.upper()
    stem = f"{start}_{end}_{spec.fingerprint}"
    return CachePaths(
        raw=base / f"{stem}.json",
        jsonl=base / f"{stem}.jsonl",
        meta=base / f"{stem}.meta.json",
        cache_key=spec.fingerprint,
        request_canonical=spec.canonical,
        endpoint=spec.submissions_path,
    )


def tickers_cache_path(cache_dir: Path) -> Path:
    return cache_dir / PROVIDER / TICKERS_FILENAME


def fetch_raw(url: str, user_agent: str) -> bytes:
    request = Request(url, headers={"User-Agent": user_agent})
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


def load_ticker_map(
    cache_dir: Path,
    user_agent: str,
    cache_only: bool,
    refresh: bool,
) -> Tuple[Dict[str, str], bytes]:
    path = tickers_cache_path(cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    raw: Optional[bytes] = None
    if cache_only:
        if not path.exists():
            raise ProviderResponseError("Cache miss and --cache-only set.")
        raw = path.read_bytes()
    else:
        if path.exists() and not refresh:
            raw = path.read_bytes()
        else:
            url = f"{SEC_BASE_URL}/files/company_tickers.json"
            raw = fetch_raw(url, user_agent)
            path.write_bytes(raw)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderResponseError("Provider response is not valid JSON.") from exc

    if not isinstance(payload, list):
        raise ProviderResponseError("Provider schema drift: tickers list invalid.")

    mapping: Dict[str, str] = {}
    for entry in payload:
        if not isinstance(entry, dict):
            raise ProviderResponseError("Provider schema drift: ticker entry invalid.")
        if "ticker" not in entry or "cik_str" not in entry:
            raise ProviderResponseError("Provider schema drift: ticker entry missing.")
        ticker = str(entry["ticker"]).upper()
        cik_str = str(entry["cik_str"])
        if not cik_str.isdigit():
            raise ProviderResponseError("Provider schema drift: CIK invalid.")
        mapping[ticker] = cik_str.zfill(10)

    return mapping, raw


def _parse_acceptance(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if len(value) != 14 or not value.isdigit():
        raise ProviderResponseError("Provider schema drift: acceptance datetime invalid.")
    year = int(value[0:4])
    month = int(value[4:6])
    day = int(value[6:8])
    hour = int(value[8:10])
    minute = int(value[10:12])
    second = int(value[12:14])
    dt = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _normalize_records(
    submissions: Dict[str, Any],
    *,
    ticker: str,
    cik_padded: str,
    start: str,
    end: str,
) -> Tuple[List[Dict[str, Any]], int]:
    filings = submissions.get("filings", {})
    recent = filings.get("recent", {})
    required = [
        "accessionNumber",
        "filingDate",
        "acceptanceDateTime",
        "form",
        "primaryDocument",
    ]
    for key in required:
        if key not in recent:
            raise ProviderResponseError("Provider schema drift: missing filings fields.")

    arrays = [recent[key] for key in required]
    if not all(isinstance(arr, list) for arr in arrays):
        raise ProviderResponseError("Provider schema drift: filings fields not lists.")
    lengths = {len(arr) for arr in arrays}
    if len(lengths) != 1:
        raise ProviderResponseError("Provider schema drift: filings list lengths mismatch.")

    records: List[Dict[str, Any]] = []
    cik_int = str(int(cik_padded))
    start_date = datetime.fromisoformat(start).date()
    end_date = datetime.fromisoformat(end).date()

    for idx in range(lengths.pop()):
        form = recent["form"][idx]
        filing_date = recent["filingDate"][idx]
        accession = recent["accessionNumber"][idx]
        acceptance = recent["acceptanceDateTime"][idx]
        primary_doc = recent["primaryDocument"][idx]

        if form not in FORMS:
            continue
        if not isinstance(filing_date, str):
            raise ProviderResponseError("Provider schema drift: filingDate invalid.")
        try:
            filing_dt = datetime.fromisoformat(filing_date).date()
        except ValueError as exc:
            raise ProviderResponseError("Provider schema drift: filingDate invalid.") from exc
        if filing_dt < start_date or filing_dt > end_date:
            continue

        acceptance_iso = _parse_acceptance(acceptance)
        accession_nodash = accession.replace("-", "")
        url_detail = (
            f"{SEC_BASE_URL}/Archives/edgar/data/{cik_int}/"
            f"{accession_nodash}/{accession}-index.html"
        )

        records.append(
            {
                "acceptance_datetime": acceptance_iso,
                "accession_number": accession,
                "cik": cik_padded,
                "filing_date": filing_date,
                "form": form,
                "primary_doc": primary_doc,
                "ticker": ticker.upper(),
                "url_filing_detail": url_detail,
            }
        )

    if not records:
        raise NoDataError("No filings in requested date range.")

    records.sort(key=lambda item: (item["filing_date"], item["accession_number"]))
    return records, len(records)


def normalize_submissions(
    raw: bytes,
    *,
    ticker: str,
    cik_padded: str,
    start: str,
    end: str,
) -> Tuple[str, int]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderResponseError("Provider response is not valid JSON.") from exc

    records, rows = _normalize_records(
        payload, ticker=ticker, cik_padded=cik_padded, start=start, end=end
    )
    lines = [json.dumps(record, sort_keys=True) for record in records]
    jsonl_text = "\n".join(lines) + "\n"
    return jsonl_text, rows


def build_meta(
    *,
    ticker: str,
    cik: str,
    start: str,
    end: str,
    request_canonical: str,
    cache_key: str,
    raw_hash: str,
    jsonl_hash: str,
    rows: int,
    cache_hit: bool,
) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "provider": PROVIDER,
        "provider_version": PROVIDER_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "ticker": ticker.upper(),
        "cik": cik,
        "start": start,
        "end": end,
        "forms": FORMS,
        "request_canonical": request_canonical,
        "cache_key": cache_key,
        "rows": int(rows),
        "source_hash": raw_hash,
        "normalized_jsonl_hash": jsonl_hash,
        "cache_hit": bool(cache_hit),
    }
