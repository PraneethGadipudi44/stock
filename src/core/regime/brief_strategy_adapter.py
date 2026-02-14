from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


ADAPTER_VERSION = "brief_strategy_adapter_v1"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class StrategyBriefError(Exception):
    pass


class StrategyBriefNoDataError(Exception):
    pass


@dataclass(frozen=True)
class CachePaths:
    strategy: Path
    meta: Path
    markdown: Path


def sha256_hex(data: bytes) -> str:
    return sha256(data).hexdigest()


def inputs_hash(as_of: str, brief_hash: str, earnings_hash: str, catalysts_hash: str) -> str:
    payload = (
        f"{as_of}\n{brief_hash}\n{earnings_hash}\n{catalysts_hash}\n".encode("utf-8")
    )
    return sha256_hex(payload)


def cache_paths(cache_dir: Path, inputs_digest: str) -> CachePaths:
    base = cache_dir / "v1" / inputs_digest
    return CachePaths(
        strategy=base / "strategy.json",
        meta=base / "strategy.meta.json",
        markdown=base / "strategy.md",
    )


def _require_keys(payload: Dict[str, Any], keys: Iterable[str], label: str) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise StrategyBriefError(f"Missing {label} keys: {', '.join(missing)}")


def load_brief_meta(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StrategyBriefError("Brief meta is not valid JSON.") from exc
    _require_keys(payload, ["normalized_brief_hash"], "brief_meta")
    return payload


def load_earnings_meta(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StrategyBriefError("Earnings meta is not valid JSON.") from exc
    _require_keys(payload, ["normalized_jsonl_hash"], "earnings_meta")
    return payload


def load_catalysts_meta(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StrategyBriefError("Catalysts meta is not valid JSON.") from exc
    _require_keys(payload, ["normalized_jsonl_hash"], "catalysts_meta")
    return payload


def _parse_date(value: str) -> date:
    if not DATE_RE.match(value):
        raise StrategyBriefError("Invalid date value.")
    year, month, day = value.split("-")
    return date(int(year), int(month), int(day))


def load_brief(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StrategyBriefError("Brief JSON is invalid.") from exc
    if not isinstance(payload, dict):
        raise StrategyBriefError("Brief JSON must be object.")
    _require_keys(
        payload,
        [
            "schema_version",
            "as_of",
            "focus_list",
            "today_catalysts",
            "recent_catalysts",
            "price_moves",
            "data_coverage",
        ],
        "brief",
    )
    return payload


def _load_jsonl(path: Path, label: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise StrategyBriefError(f"{label} JSONL contains invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise StrategyBriefError(f"{label} JSONL record must be object.")
        records.append(payload)
    return records


def _require_record_keys(records: List[Dict[str, Any]], keys: Iterable[str], label: str) -> None:
    for record in records:
        _require_keys(record, keys, label)


def _round_float(value: Optional[float], dp: int) -> Optional[float]:
    if value is None:
        return None
    return float(f"{value:.{dp}f}")


def _build_summary(
    *,
    ticker: str,
    pct_1d: Optional[float],
    catalyst_form: Optional[str],
    earnings_date: Optional[str],
) -> str:
    parts = [f"{ticker}:"]
    if pct_1d is not None:
        parts.append(f"1d move {pct_1d:+.2%}")
    if catalyst_form:
        parts.append(f"Catalyst today: {catalyst_form}")
    if earnings_date:
        parts.append(f"Earnings: {earnings_date}")
    parts.append("Monitor for follow-through.")
    summary = " ".join(parts)
    return summary


def build_strategy(
    *,
    as_of: str,
    brief: Dict[str, Any],
    earnings_records: List[Dict[str, Any]],
    catalysts_records: List[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, int]]:
    if not DATE_RE.match(as_of):
        raise StrategyBriefError("Invalid as_of date.")
    if brief.get("as_of") != as_of:
        raise StrategyBriefNoDataError("Brief as_of does not match requested as_of.")

    focus_list = brief.get("focus_list", [])
    price_moves = brief.get("price_moves", [])
    if not focus_list or not price_moves:
        raise StrategyBriefNoDataError("Brief focus_list or price_moves is empty.")

    earnings_by_ticker: Dict[str, List[str]] = {}
    for record in earnings_records:
        ticker = str(record.get("ticker", "")).upper()
        event_date = record.get("event_date")
        if ticker and event_date:
            earnings_by_ticker.setdefault(ticker, []).append(event_date)
    for ticker in earnings_by_ticker:
        earnings_by_ticker[ticker] = sorted(set(earnings_by_ticker[ticker]))

    catalysts_today = brief.get("today_catalysts", [])
    catalysts_recent = brief.get("recent_catalysts", [])

    catalysts_today_by_ticker: Dict[str, List[str]] = {}
    for record in catalysts_today:
        ticker = str(record.get("ticker", "")).upper()
        form = record.get("form")
        if ticker and form:
            catalysts_today_by_ticker.setdefault(ticker, []).append(form)
    for ticker in catalysts_today_by_ticker:
        catalysts_today_by_ticker[ticker] = sorted(catalysts_today_by_ticker[ticker])

    price_by_ticker: Dict[str, Dict[str, Any]] = {}
    for item in price_moves:
        ticker = str(item.get("ticker", "")).upper()
        if ticker:
            price_by_ticker[ticker] = item

    as_of_date = _parse_date(as_of)
    window_end = as_of_date + timedelta(days=5)

    signals: List[Dict[str, Any]] = []

    for entry in focus_list:
        ticker = str(entry.get("ticker", "")).upper()
        if not ticker:
            continue
        base_score = float(entry.get("score", 0.0))
        has_today = bool(entry.get("has_catalyst_today", False))
        has_recent = bool(entry.get("has_recent_catalyst", False))

        pct_1d_raw = None
        if ticker in price_by_ticker:
            pct_1d_raw = price_by_ticker[ticker].get("pct_1d")
        pct_1d = _round_float(pct_1d_raw, 6)

        earnings_dates = earnings_by_ticker.get(ticker, [])
        earnings_within = [
            d for d in earnings_dates
            if _parse_date(d) >= as_of_date and _parse_date(d) <= window_end
        ]
        has_earnings = bool(earnings_within)
        earnings_date = earnings_within[0] if has_earnings else None

        score = base_score + (7.0 if has_earnings else 0.0)

        if score >= 20 or has_today or has_earnings:
            priority = "high"
        elif score >= 10:
            priority = "medium"
        else:
            priority = "low"

        tags: List[str] = []
        if pct_1d is not None:
            tags.append("move_1d")
        if has_today:
            tags.append("catalyst_today")
        if has_recent:
            tags.append("catalyst_recent")
        if has_earnings:
            tags.append("earnings_soon")
        if not tags:
            tags.append("focus")
        tags = sorted(set(tags))
        if len(tags) > 5:
            tags = tags[:5]

        catalyst_form = None
        forms_today = catalysts_today_by_ticker.get(ticker)
        if forms_today:
            catalyst_form = forms_today[0]

        summary = _build_summary(
            ticker=ticker,
            pct_1d=pct_1d,
            catalyst_form=catalyst_form,
            earnings_date=earnings_date,
        )

        signals.append(
            {
                "ticker": ticker,
                "priority": priority,
                "score": float(f"{score:.4f}"),
                "tags": tags,
                "summary": summary,
                "inputs": {
                    "pct_1d": pct_1d,
                    "has_catalyst_today": bool(has_today),
                    "has_recent_catalyst": bool(has_recent),
                    "has_earnings_within_5d": bool(has_earnings),
                    "earnings_event_date": earnings_date,
                },
            }
        )

    signals.sort(
        key=lambda item: (
            {"high": 0, "medium": 1, "low": 2}.get(item["priority"], 3),
            -item["score"],
            item["ticker"],
        )
    )

    def _dedupe_sorted(items: Iterable[str]) -> List[str]:
        return sorted(set(items))

    watchlist = _dedupe_sorted([s["ticker"] for s in signals[:10]])
    event_risk = _dedupe_sorted(
        [
            s["ticker"]
            for s in signals
            if s["inputs"]["has_catalyst_today"]
            or s["inputs"]["has_earnings_within_5d"]
        ]
    )
    momentum = _dedupe_sorted(
        [
            s["ticker"]
            for s in signals
            if s["inputs"]["pct_1d"] is not None
            and abs(s["inputs"]["pct_1d"]) >= 0.03
        ]
    )

    coverage = {
        "brief_focus_count": len(focus_list),
        "today_catalysts_count": len(catalysts_today),
        "recent_catalysts_count": len(catalysts_recent),
        "earnings_rows": len(earnings_records),
        "signals_rows": len(signals),
    }

    strategy = {
        "schema_version": 1,
        "as_of": as_of,
        "signals": signals,
        "playbook": {
            "watchlist": watchlist,
            "event_risk": event_risk,
            "momentum": momentum,
        },
        "coverage": coverage,
    }

    rows_meta = {
        "signals": len(signals),
        "playbook_watchlist": len(watchlist),
        "playbook_event_risk": len(event_risk),
        "playbook_momentum": len(momentum),
    }
    return strategy, rows_meta


def render_markdown(strategy: Dict[str, Any]) -> str:
    lines = [f"# Strategy ({strategy['as_of']})", ""]
    lines.append("## Signals")
    for item in strategy["signals"]:
        lines.append(
            f"- {item['ticker']}: {item['priority']} score={item['score']:.4f} ({item['summary']})"
        )
    lines.append("")
    lines.append("## Playbook")
    lines.append(f"- watchlist: {', '.join(strategy['playbook']['watchlist'])}")
    lines.append(f"- event_risk: {', '.join(strategy['playbook']['event_risk'])}")
    lines.append(f"- momentum: {', '.join(strategy['playbook']['momentum'])}")
    lines.append("")
    return "\n".join(lines) + "\n"


def build_meta(
    *,
    brief_hash: str,
    earnings_hash: str,
    catalysts_hash: str,
    inputs_digest: str,
    strategy_hash: str,
    markdown_hash: Optional[str],
    rows: Dict[str, int],
    cache_hit: bool,
) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "adapter_version": ADAPTER_VERSION,
        "inputs": {
            "brief": {"normalized_brief_hash": brief_hash},
            "earnings": {"normalized_jsonl_hash": earnings_hash},
            "catalysts": {"normalized_jsonl_hash": catalysts_hash},
        },
        "inputs_hash": inputs_digest,
        "normalized_strategy_hash": strategy_hash,
        "markdown_hash": markdown_hash,
        "rows": rows,
        "cache_hit": bool(cache_hit),
    }
