from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple


ADAPTER_VERSION = "strategy_brief_trace_adapter_v1"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class StrategyBriefTraceMetaError(Exception):
    pass


class StrategyBriefTraceDataError(Exception):
    pass


class StrategyBriefTraceNoDataError(Exception):
    pass


@dataclass(frozen=True)
class CachePaths:
    trace: Path
    meta: Path


def sha256_hex(data: bytes) -> str:
    return sha256(data).hexdigest()


def inputs_hash(
    as_of: str,
    brief_hash: str,
    earnings_hash: str,
    catalysts_hash: str,
    strategy_hash: str,
    markdown_hash: Optional[str],
) -> str:
    markdown_part = markdown_hash or ""
    payload = (
        f"{as_of}\n{brief_hash}\n{earnings_hash}\n{catalysts_hash}\n"
        f"{strategy_hash}\n{markdown_part}\n".encode("utf-8")
    )
    return sha256_hex(payload)


def cache_paths(cache_dir: Path, inputs_digest: str) -> CachePaths:
    base = cache_dir / "strategy-brief" / "v1" / inputs_digest
    return CachePaths(
        trace=base / "trace.json",
        meta=base / "trace.meta.json",
    )


def _require_keys(payload: Dict[str, Any], keys: Iterable[str], label: str) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise StrategyBriefTraceMetaError(f"Missing {label} keys: {', '.join(missing)}")


def load_brief_meta(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StrategyBriefTraceMetaError("Brief meta is not valid JSON.") from exc
    _require_keys(payload, ["normalized_brief_hash"], "brief_meta")
    return payload


def load_earnings_meta(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StrategyBriefTraceMetaError("Earnings meta is not valid JSON.") from exc
    _require_keys(payload, ["normalized_jsonl_hash"], "earnings_meta")
    return payload


def load_catalysts_meta(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StrategyBriefTraceMetaError("Catalysts meta is not valid JSON.") from exc
    _require_keys(payload, ["normalized_jsonl_hash"], "catalysts_meta")
    return payload


def load_strategy_meta(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StrategyBriefTraceMetaError("Strategy meta is not valid JSON.") from exc
    _require_keys(payload, ["normalized_strategy_hash"], "strategy_meta")
    return payload


def load_strategy(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StrategyBriefTraceDataError("Strategy JSON is invalid.") from exc
    if not isinstance(payload, dict):
        raise StrategyBriefTraceDataError("Strategy JSON must be object.")
    if "as_of" not in payload:
        raise StrategyBriefTraceDataError("Strategy JSON missing as_of.")
    if not DATE_RE.match(str(payload.get("as_of", ""))):
        raise StrategyBriefTraceDataError("Strategy as_of must be YYYY-MM-DD.")
    signals = payload.get("signals")
    playbook = payload.get("playbook")
    if not isinstance(signals, list):
        raise StrategyBriefTraceDataError("Strategy signals must be array.")
    if not isinstance(playbook, dict):
        raise StrategyBriefTraceDataError("Strategy playbook must be object.")
    for key in ("watchlist", "event_risk", "momentum"):
        if key not in playbook:
            raise StrategyBriefTraceDataError("Strategy playbook missing required keys.")
        if not isinstance(playbook[key], list):
            raise StrategyBriefTraceDataError("Strategy playbook entries must be arrays.")
    return payload


def _coverage_from_strategy(strategy: Dict[str, Any]) -> Dict[str, int]:
    playbook = strategy.get("playbook", {})
    return {
        "signals_rows": len(strategy.get("signals", [])),
        "playbook_watchlist": len(playbook.get("watchlist", [])),
        "playbook_event_risk": len(playbook.get("event_risk", [])),
        "playbook_momentum": len(playbook.get("momentum", [])),
    }


def build_trace(
    *,
    as_of: str,
    brief_hash: str,
    earnings_hash: str,
    catalysts_hash: str,
    strategy_hash: str,
    markdown_hash: Optional[str],
    coverage: Dict[str, int],
) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "as_of": as_of,
        "inputs_hash": inputs_hash(
            as_of, brief_hash, earnings_hash, catalysts_hash, strategy_hash, markdown_hash
        ),
        "artifacts": {
            "brief": {"normalized_brief_hash": brief_hash},
            "earnings": {"normalized_jsonl_hash": earnings_hash},
            "catalysts": {"normalized_jsonl_hash": catalysts_hash},
            "strategy": {"normalized_strategy_hash": strategy_hash},
            "markdown": {"markdown_hash": markdown_hash},
        },
        "coverage": coverage,
    }


def build_trace_meta(
    *,
    brief_hash: str,
    earnings_hash: str,
    catalysts_hash: str,
    strategy_hash: str,
    markdown_hash: Optional[str],
    inputs_digest: str,
    trace_hash: str,
    coverage: Dict[str, int],
    cache_hit: bool,
) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "adapter_version": ADAPTER_VERSION,
        "inputs": {
            "brief": {"normalized_brief_hash": brief_hash},
            "earnings": {"normalized_jsonl_hash": earnings_hash},
            "catalysts": {"normalized_jsonl_hash": catalysts_hash},
            "strategy": {"normalized_strategy_hash": strategy_hash},
            "markdown": {"markdown_hash": markdown_hash},
        },
        "inputs_hash": inputs_digest,
        "normalized_trace_hash": trace_hash,
        "rows": coverage,
        "cache_hit": bool(cache_hit),
    }


def strategy_coverage(strategy: Dict[str, Any]) -> Dict[str, int]:
    return _coverage_from_strategy(strategy)
