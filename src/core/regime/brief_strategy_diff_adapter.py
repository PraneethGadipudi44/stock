from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


ADAPTER_VERSION = "brief_strategy_diff_adapter_v1"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class BriefStrategyDiffMetaError(Exception):
    pass


class BriefStrategyDiffDataError(Exception):
    pass


class BriefStrategyDiffNoDataError(Exception):
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
    left_strategy_hash: str,
    left_markdown_hash: Optional[str],
    right_as_of: str,
    right_inputs_hash: str,
    right_strategy_hash: str,
    right_markdown_hash: Optional[str],
) -> str:
    payload = (
        f"{left_as_of}\n{left_inputs_hash}\n{left_strategy_hash}\n"
        f"{left_markdown_hash or ''}\n{right_as_of}\n{right_inputs_hash}\n"
        f"{right_strategy_hash}\n{right_markdown_hash or ''}\n"
    ).encode("utf-8")
    return sha256_hex(payload)


def cache_paths(cache_dir: Path, inputs_digest: str) -> CachePaths:
    base = cache_dir / "brief-strategy" / "v1" / inputs_digest
    return CachePaths(
        diff=base / "diff.json",
        meta=base / "diff.meta.json",
    )


def _require_keys(payload: Dict[str, Any], keys: Iterable[str], label: str) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise BriefStrategyDiffMetaError(f"Missing {label} keys: {', '.join(missing)}")


def load_strategy_meta(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BriefStrategyDiffMetaError("Strategy meta is not valid JSON.") from exc
    _require_keys(
        payload,
        ["normalized_strategy_hash", "inputs_hash", "markdown_hash", "inputs"],
        "strategy_meta",
    )
    inputs = payload.get("inputs", {})
    if not isinstance(inputs, dict):
        raise BriefStrategyDiffMetaError("Strategy meta inputs must be object.")
    _require_keys(inputs, ["brief", "earnings", "catalysts"], "strategy_meta.inputs")
    for section, field in [
        ("brief", "normalized_brief_hash"),
        ("earnings", "normalized_jsonl_hash"),
        ("catalysts", "normalized_jsonl_hash"),
    ]:
        if section not in inputs or field not in inputs.get(section, {}):
            raise BriefStrategyDiffMetaError("Strategy meta inputs missing fields.")
    return payload


def load_strategy(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BriefStrategyDiffDataError("Strategy JSON is invalid.") from exc
    if not isinstance(payload, dict):
        raise BriefStrategyDiffDataError("Strategy JSON must be object.")
    for key in ("as_of", "signals", "playbook"):
        if key not in payload:
            raise BriefStrategyDiffNoDataError("Strategy JSON missing required keys.")
    as_of = str(payload.get("as_of", ""))
    if not DATE_RE.match(as_of):
        raise BriefStrategyDiffDataError("Strategy as_of must be YYYY-MM-DD.")
    if not isinstance(payload.get("signals"), list):
        raise BriefStrategyDiffDataError("Strategy signals must be array.")
    playbook = payload.get("playbook")
    if not isinstance(playbook, dict):
        raise BriefStrategyDiffDataError("Strategy playbook must be object.")
    for key in ("watchlist", "event_risk", "momentum"):
        if key not in playbook:
            raise BriefStrategyDiffNoDataError("Strategy playbook missing required keys.")
        if not isinstance(playbook[key], list):
            raise BriefStrategyDiffDataError("Strategy playbook entries must be arrays.")
    return payload


def _coverage(strategy: Dict[str, Any]) -> Dict[str, int]:
    playbook = strategy.get("playbook", {})
    return {
        "signals": len(strategy.get("signals", [])),
        "watchlist": len(playbook.get("watchlist", [])),
        "event_risk": len(playbook.get("event_risk", [])),
        "momentum": len(playbook.get("momentum", [])),
    }


def _summary(
    *,
    left_as_of: str,
    right_as_of: str,
    left_counts: Dict[str, int],
    right_counts: Dict[str, int],
    changes: Dict[str, bool],
) -> list[str]:
    signals_delta = right_counts["signals"] - left_counts["signals"]
    watchlist_delta = right_counts["watchlist"] - left_counts["watchlist"]
    event_risk_delta = right_counts["event_risk"] - left_counts["event_risk"]
    momentum_delta = right_counts["momentum"] - left_counts["momentum"]

    lines = [
        f"as_of: {left_as_of} -> {right_as_of}",
        f"signals: {signals_delta:+d} (right {right_counts['signals']} vs left {left_counts['signals']})",
        (
            "playbook: "
            f"watchlist {watchlist_delta:+d}, "
            f"event_risk {event_risk_delta:+d}, "
            f"momentum {momentum_delta:+d}"
        ),
    ]

    if changes["strategy_changed"] or changes["markdown_changed"]:
        lines.append(
            "changed: "
            f"strategy={str(changes['strategy_changed']).lower()}, "
            f"markdown={str(changes['markdown_changed']).lower()}"
        )
    return lines


def build_diff(
    *,
    left_strategy: Dict[str, Any],
    right_strategy: Dict[str, Any],
    left_strategy_hash: str,
    right_strategy_hash: str,
    left_inputs_hash: str,
    right_inputs_hash: str,
    left_markdown_hash: Optional[str],
    right_markdown_hash: Optional[str],
    inputs_digest: str,
) -> Dict[str, Any]:
    left_counts = _coverage(left_strategy)
    right_counts = _coverage(right_strategy)

    changes = {
        "as_of_changed": left_strategy["as_of"] != right_strategy["as_of"],
        "strategy_changed": left_strategy_hash != right_strategy_hash,
        "markdown_changed": left_markdown_hash != right_markdown_hash,
    }

    summary = _summary(
        left_as_of=left_strategy["as_of"],
        right_as_of=right_strategy["as_of"],
        left_counts=left_counts,
        right_counts=right_counts,
        changes=changes,
    )

    return {
        "schema_version": 1,
        "left": {
            "as_of": left_strategy["as_of"],
            "normalized_strategy_hash": left_strategy_hash,
            "inputs_hash": left_inputs_hash,
            "markdown_hash": left_markdown_hash,
        },
        "right": {
            "as_of": right_strategy["as_of"],
            "normalized_strategy_hash": right_strategy_hash,
            "inputs_hash": right_inputs_hash,
            "markdown_hash": right_markdown_hash,
        },
        "inputs_hash": inputs_digest,
        "changes": changes,
        "coverage_delta": {
            "signals_delta": right_counts["signals"] - left_counts["signals"],
            "watchlist_delta": right_counts["watchlist"] - left_counts["watchlist"],
            "event_risk_delta": right_counts["event_risk"] - left_counts["event_risk"],
            "momentum_delta": right_counts["momentum"] - left_counts["momentum"],
        },
        "summary": summary,
    }


def build_meta(
    *,
    left_strategy_hash: str,
    right_strategy_hash: str,
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
                "normalized_strategy_hash": left_strategy_hash,
                "inputs_hash": left_inputs_hash,
                "markdown_hash": left_markdown_hash,
            },
            "right": {
                "normalized_strategy_hash": right_strategy_hash,
                "inputs_hash": right_inputs_hash,
                "markdown_hash": right_markdown_hash,
            },
        },
        "inputs_hash": inputs_digest,
        "normalized_diff_hash": diff_hash,
        "rows": {"nonzero_deltas_count": nonzero_deltas},
        "cache_hit": bool(cache_hit),
    }


def count_nonzero_deltas(coverage_delta: Dict[str, int]) -> int:
    return sum(1 for value in coverage_delta.values() if value != 0)
