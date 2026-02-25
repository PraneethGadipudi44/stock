from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .brief_adapter import inputs_hash as brief_inputs_hash
from .brief_strategy_adapter import inputs_hash as strategy_inputs_hash
from .brief_strategy_diff_adapter import inputs_hash as strategy_diff_inputs_hash
from .strategy_brief_trace_adapter import inputs_hash as trace_inputs_hash
from .strategy_brief_trace_diff_adapter import inputs_hash as trace_diff_inputs_hash


ADAPTER_VERSION = "audit_manifest_adapter_v1"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class AuditManifestMetaError(Exception):
    pass


class AuditManifestDataError(Exception):
    pass


class AuditManifestNoDataError(Exception):
    pass


@dataclass(frozen=True)
class CachePaths:
    manifest: Path
    meta: Path


def sha256_hex(data: bytes) -> str:
    return sha256(data).hexdigest()


def inputs_hash(
    *,
    as_of: str,
    brief_hash: str,
    brief_inputs_hash_value: str,
    strategy_hash: str,
    strategy_inputs_hash_value: str,
    strategy_markdown_hash: Optional[str],
    trace_hash: str,
    trace_inputs_hash_value: str,
    diff_strategy_hash: str,
    diff_strategy_inputs_hash_value: str,
    diff_trace_hash: str,
    diff_trace_inputs_hash_value: str,
    diff_strategy_md_hash: Optional[str],
    diff_trace_md_hash: Optional[str],
) -> str:
    payload = (
        f"{as_of}\n"
        f"{brief_hash}\n"
        f"{brief_inputs_hash_value}\n"
        f"{strategy_hash}\n"
        f"{strategy_inputs_hash_value}\n"
        f"{strategy_markdown_hash or ''}\n"
        f"{trace_hash}\n"
        f"{trace_inputs_hash_value}\n"
        f"{diff_strategy_hash}\n"
        f"{diff_strategy_inputs_hash_value}\n"
        f"{diff_trace_hash}\n"
        f"{diff_trace_inputs_hash_value}\n"
        f"{diff_strategy_md_hash or ''}\n"
        f"{diff_trace_md_hash or ''}\n"
    ).encode("utf-8")
    return sha256_hex(payload)


def cache_paths(cache_dir: Path, inputs_digest: str) -> CachePaths:
    base = cache_dir / "v1" / inputs_digest
    return CachePaths(
        manifest=base / "manifest.json",
        meta=base / "manifest.meta.json",
    )


def _require_keys(payload: Dict[str, Any], keys: Iterable[str], label: str) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise AuditManifestMetaError(f"Missing {label} keys: {', '.join(missing)}")


def _load_json(path: Path, label: str) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AuditManifestDataError(f"{label} is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise AuditManifestDataError(f"{label} must be JSON object.")
    return payload


def load_brief(path: Path) -> Dict[str, Any]:
    payload = _load_json(path, "Brief")
    _require_keys(payload, ["as_of"], "brief")
    if not DATE_RE.match(str(payload.get("as_of", ""))):
        raise AuditManifestDataError("Brief as_of must be YYYY-MM-DD.")
    return payload


def load_strategy(path: Path) -> Dict[str, Any]:
    payload = _load_json(path, "Strategy")
    _require_keys(payload, ["as_of", "signals", "playbook"], "strategy")
    if not DATE_RE.match(str(payload.get("as_of", ""))):
        raise AuditManifestDataError("Strategy as_of must be YYYY-MM-DD.")
    return payload


def load_trace(path: Path) -> Dict[str, Any]:
    payload = _load_json(path, "Trace")
    _require_keys(payload, ["as_of", "inputs_hash", "artifacts"], "trace")
    if not DATE_RE.match(str(payload.get("as_of", ""))):
        raise AuditManifestDataError("Trace as_of must be YYYY-MM-DD.")
    return payload


def load_diff(path: Path, label: str) -> Dict[str, Any]:
    payload = _load_json(path, label)
    _require_keys(payload, ["left", "right", "inputs_hash"], f"{label.lower()}")
    for side in ("left", "right"):
        if "as_of" not in payload[side]:
            raise AuditManifestNoDataError(f"{label} missing {side}.as_of")
        if not DATE_RE.match(str(payload[side].get("as_of", ""))):
            raise AuditManifestDataError(f"{label} {side}.as_of must be YYYY-MM-DD.")
    return payload


def load_brief_meta(path: Path) -> Dict[str, Any]:
    payload = _load_json(path, "Brief meta")
    _require_keys(
        payload, ["normalized_brief_hash", "inputs_hash", "inputs"], "brief_meta"
    )
    inputs = payload.get("inputs", {})
    if not isinstance(inputs, dict):
        raise AuditManifestMetaError("Brief meta inputs must be object.")
    _require_keys(inputs, ["prices", "filings", "catalysts"], "brief_meta.inputs")
    return payload


def load_strategy_meta(path: Path) -> Dict[str, Any]:
    payload = _load_json(path, "Strategy meta")
    _require_keys(
        payload,
        ["normalized_strategy_hash", "inputs_hash", "markdown_hash", "inputs"],
        "strategy_meta",
    )
    inputs = payload.get("inputs", {})
    if not isinstance(inputs, dict):
        raise AuditManifestMetaError("Strategy meta inputs must be object.")
    _require_keys(inputs, ["brief", "earnings", "catalysts"], "strategy_meta.inputs")
    return payload


def load_trace_meta(path: Path) -> Dict[str, Any]:
    payload = _load_json(path, "Trace meta")
    _require_keys(payload, ["normalized_trace_hash", "inputs_hash", "inputs"], "trace_meta")
    inputs = payload.get("inputs", {})
    if not isinstance(inputs, dict):
        raise AuditManifestMetaError("Trace meta inputs must be object.")
    _require_keys(
        inputs,
        ["brief", "earnings", "catalysts", "strategy", "markdown"],
        "trace_meta.inputs",
    )
    return payload


def load_diff_meta(path: Path, label: str) -> Dict[str, Any]:
    payload = _load_json(path, f"{label} meta")
    _require_keys(payload, ["normalized_diff_hash", "inputs_hash", "inputs"], f"{label}_meta")
    inputs = payload.get("inputs", {})
    if not isinstance(inputs, dict):
        raise AuditManifestMetaError(f"{label} meta inputs must be object.")
    _require_keys(inputs, ["left", "right"], f"{label}_meta.inputs")
    return payload


def build_manifest(
    *,
    as_of: str,
    brief_hash: str,
    brief_inputs_hash_value: str,
    strategy_hash: str,
    strategy_inputs_hash_value: str,
    strategy_markdown_hash: Optional[str],
    trace_hash: str,
    trace_inputs_hash_value: str,
    diff_strategy_hash: str,
    diff_strategy_inputs_hash_value: str,
    diff_trace_hash: str,
    diff_trace_inputs_hash_value: str,
    diff_strategy_md_hash: Optional[str],
    diff_trace_md_hash: Optional[str],
    inputs_digest: str,
) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "as_of": as_of,
        "inputs_hash": inputs_digest,
        "artifacts": {
            "brief": {
                "normalized_brief_hash": brief_hash,
                "inputs_hash": brief_inputs_hash_value,
            },
            "strategy": {
                "normalized_strategy_hash": strategy_hash,
                "inputs_hash": strategy_inputs_hash_value,
                "markdown_hash": strategy_markdown_hash,
            },
            "trace_strategy_brief": {
                "normalized_trace_hash": trace_hash,
                "inputs_hash": trace_inputs_hash_value,
            },
            "diff_strategy_brief": {
                "normalized_diff_hash": diff_strategy_hash,
                "inputs_hash": diff_strategy_inputs_hash_value,
            },
            "diff_trace_strategy_brief": {
                "normalized_diff_hash": diff_trace_hash,
                "inputs_hash": diff_trace_inputs_hash_value,
            },
            "markdown": {
                "brief_strategy_diff_md_hash": diff_strategy_md_hash,
                "trace_strategy_diff_md_hash": diff_trace_md_hash,
            },
        },
    }


def build_meta(
    *,
    manifest: Dict[str, Any],
    inputs_digest: str,
    manifest_hash: str,
    cache_hit: bool,
) -> Dict[str, Any]:
    artifacts = manifest["artifacts"]
    return {
        "schema_version": 1,
        "adapter_version": ADAPTER_VERSION,
        "inputs": {
            "brief": artifacts["brief"],
            "strategy": artifacts["strategy"],
            "trace_strategy_brief": artifacts["trace_strategy_brief"],
            "diff_strategy_brief": artifacts["diff_strategy_brief"],
            "diff_trace_strategy_brief": artifacts["diff_trace_strategy_brief"],
            "markdown": artifacts["markdown"],
        },
        "inputs_hash": inputs_digest,
        "normalized_manifest_hash": manifest_hash,
        "rows": {"artifact_count": len(artifacts)},
        "cache_hit": bool(cache_hit),
    }
