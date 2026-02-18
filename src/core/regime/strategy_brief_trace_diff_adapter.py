from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


ADAPTER_VERSION = "strategy_brief_trace_diff_adapter_v1"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class StrategyBriefTraceDiffMetaError(Exception):
    pass


class StrategyBriefTraceDiffDataError(Exception):
    pass


class StrategyBriefTraceDiffNoDataError(Exception):
    pass


@dataclass(frozen=True)
class CachePaths:
    diff: Path
    meta: Path


def sha256_hex(data: bytes) -> str:
    return sha256(data).hexdigest()


def inputs_hash(
    *,
    left_as_of: str,
    left_inputs_hash: str,
    left_trace_hash: str,
    left_markdown_hash: Optional[str],
    right_as_of: str,
    right_inputs_hash: str,
    right_trace_hash: str,
    right_markdown_hash: Optional[str],
) -> str:
    payload = (
        f"{left_as_of}\n{left_inputs_hash}\n{left_trace_hash}\n"
        f"{left_markdown_hash or ''}\n{right_as_of}\n{right_inputs_hash}\n"
        f"{right_trace_hash}\n{right_markdown_hash or ''}\n"
    ).encode("utf-8")
    return sha256_hex(payload)


def cache_paths(cache_dir: Path, inputs_digest: str) -> CachePaths:
    base = cache_dir / "strategy-brief" / "v1" / inputs_digest
    return CachePaths(
        diff=base / "diff.json",
        meta=base / "diff.meta.json",
    )


def _require_keys(payload: Dict[str, Any], keys: Iterable[str], label: str) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise StrategyBriefTraceDiffMetaError(
            f"Missing {label} keys: {', '.join(missing)}"
        )


def load_trace_meta(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StrategyBriefTraceDiffMetaError("Trace meta is not valid JSON.") from exc
    _require_keys(payload, ["normalized_trace_hash", "inputs_hash"], "trace_meta")
    return payload


def load_trace(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StrategyBriefTraceDiffDataError("Trace JSON is invalid.") from exc
    if not isinstance(payload, dict):
        raise StrategyBriefTraceDiffDataError("Trace JSON must be object.")
    required = ["schema_version", "as_of", "inputs_hash", "artifacts", "coverage"]
    for key in required:
        if key not in payload:
            raise StrategyBriefTraceDiffNoDataError("Trace JSON missing required keys.")
    as_of = str(payload.get("as_of", ""))
    if not DATE_RE.match(as_of):
        raise StrategyBriefTraceDiffDataError("Trace as_of must be YYYY-MM-DD.")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        raise StrategyBriefTraceDiffDataError("Trace artifacts must be object.")
    for section, field in [
        ("brief", "normalized_brief_hash"),
        ("earnings", "normalized_jsonl_hash"),
        ("catalysts", "normalized_jsonl_hash"),
        ("strategy", "normalized_strategy_hash"),
        ("markdown", "markdown_hash"),
    ]:
        if section not in artifacts or field not in artifacts.get(section, {}):
            raise StrategyBriefTraceDiffNoDataError("Trace artifacts missing fields.")
    coverage = payload.get("coverage")
    if not isinstance(coverage, dict):
        raise StrategyBriefTraceDiffDataError("Trace coverage must be object.")
    return payload


def build_diff(
    *,
    left_trace: Dict[str, Any],
    right_trace: Dict[str, Any],
    left_trace_hash: str,
    right_trace_hash: str,
    inputs_digest: str,
) -> Dict[str, Any]:
    def _extract_artifacts(trace: Dict[str, Any]) -> Dict[str, Any]:
        artifacts = trace["artifacts"]
        return {
            "brief": {
                "normalized_brief_hash": artifacts["brief"]["normalized_brief_hash"]
            },
            "earnings": {
                "normalized_jsonl_hash": artifacts["earnings"]["normalized_jsonl_hash"]
            },
            "catalysts": {
                "normalized_jsonl_hash": artifacts["catalysts"]["normalized_jsonl_hash"]
            },
            "strategy": {
                "normalized_strategy_hash": artifacts["strategy"][
                    "normalized_strategy_hash"
                ]
            },
            "markdown": {"markdown_hash": artifacts["markdown"]["markdown_hash"]},
        }

    left_artifacts = _extract_artifacts(left_trace)
    right_artifacts = _extract_artifacts(right_trace)

    diff_payload = {
        "schema_version": 1,
        "left": {
            "as_of": left_trace["as_of"],
            "inputs_hash": left_trace["inputs_hash"],
            "normalized_trace_hash": left_trace_hash,
            "artifacts": left_artifacts,
        },
        "right": {
            "as_of": right_trace["as_of"],
            "inputs_hash": right_trace["inputs_hash"],
            "normalized_trace_hash": right_trace_hash,
            "artifacts": right_artifacts,
        },
        "inputs_hash": inputs_digest,
        "changes": {
            "as_of_changed": left_trace["as_of"] != right_trace["as_of"],
            "brief_changed": (
                left_artifacts["brief"]["normalized_brief_hash"]
                != right_artifacts["brief"]["normalized_brief_hash"]
            ),
            "earnings_changed": (
                left_artifacts["earnings"]["normalized_jsonl_hash"]
                != right_artifacts["earnings"]["normalized_jsonl_hash"]
            ),
            "catalysts_changed": (
                left_artifacts["catalysts"]["normalized_jsonl_hash"]
                != right_artifacts["catalysts"]["normalized_jsonl_hash"]
            ),
            "strategy_changed": (
                left_artifacts["strategy"]["normalized_strategy_hash"]
                != right_artifacts["strategy"]["normalized_strategy_hash"]
            ),
            "markdown_changed": (
                left_artifacts["markdown"]["markdown_hash"]
                != right_artifacts["markdown"]["markdown_hash"]
            ),
            "trace_changed": left_trace_hash != right_trace_hash,
        },
        "coverage_delta": {
            "signals_rows_delta": right_trace["coverage"]["signals_rows"]
            - left_trace["coverage"]["signals_rows"],
            "playbook_watchlist_delta": right_trace["coverage"]["playbook_watchlist"]
            - left_trace["coverage"]["playbook_watchlist"],
            "playbook_event_risk_delta": right_trace["coverage"]["playbook_event_risk"]
            - left_trace["coverage"]["playbook_event_risk"],
            "playbook_momentum_delta": right_trace["coverage"]["playbook_momentum"]
            - left_trace["coverage"]["playbook_momentum"],
        },
    }
    return diff_payload


def build_meta(
    *,
    left_trace_hash: str,
    right_trace_hash: str,
    left_inputs_hash: str,
    right_inputs_hash: str,
    left_markdown_hash: Optional[str],
    right_markdown_hash: Optional[str],
    inputs_digest: str,
    diff_hash: str,
    nonzero_deltas: int,
    cache_hit: bool,
) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "adapter_version": ADAPTER_VERSION,
        "inputs": {
            "left": {
                "normalized_trace_hash": left_trace_hash,
                "inputs_hash": left_inputs_hash,
                "markdown_hash": left_markdown_hash,
            },
            "right": {
                "normalized_trace_hash": right_trace_hash,
                "inputs_hash": right_inputs_hash,
                "markdown_hash": right_markdown_hash,
            },
        },
        "inputs_hash": inputs_digest,
        "normalized_diff_hash": diff_hash,
        "rows": {
            "nonzero_deltas_count": nonzero_deltas,
        },
        "cache_hit": bool(cache_hit),
    }


def count_nonzero_deltas(coverage_delta: Dict[str, int]) -> int:
    return sum(1 for value in coverage_delta.values() if value != 0)
