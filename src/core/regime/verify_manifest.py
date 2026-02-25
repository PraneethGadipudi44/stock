from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

from .brief_adapter import inputs_hash as brief_inputs_hash
from .brief_strategy_adapter import inputs_hash as strategy_inputs_hash
from .brief_strategy_diff_adapter import inputs_hash as strategy_diff_inputs_hash
from .strategy_brief_trace_adapter import inputs_hash as trace_inputs_hash
from .strategy_brief_trace_diff_adapter import inputs_hash as trace_diff_inputs_hash
from .audit_manifest_adapter import inputs_hash as manifest_inputs_hash


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class VerifyManifestError(Exception):
    pass


class VerifyManifestMetaError(VerifyManifestError):
    pass


class VerifyManifestDataError(VerifyManifestError):
    pass


class VerifyManifestNoDataError(VerifyManifestError):
    pass


class VerifyManifestIntegrityError(VerifyManifestError):
    pass


@dataclass(frozen=True)
class VerificationResult:
    report: Optional[Dict[str, Any]]


def sha256_hex(data: bytes) -> str:
    return sha256(data).hexdigest()


def _require_keys(payload: Dict[str, Any], keys: Iterable[str], label: str) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise VerifyManifestNoDataError(f"Missing {label} keys: {', '.join(missing)}")


def _load_json(path: Path, label: str) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise VerifyManifestDataError(f"{label} is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise VerifyManifestDataError(f"{label} must be JSON object.")
    return payload


def _check_date(value: str, label: str) -> None:
    if not DATE_RE.match(value):
        raise VerifyManifestDataError(f"{label} must be YYYY-MM-DD.")


def _check_inputs_hash(
    label: str, expected: str, actual: str, *, mismatch_message: str
) -> None:
    if expected != actual:
        raise VerifyManifestIntegrityError(mismatch_message)


def verify_manifest(
    *,
    manifest_path: Path,
    manifest_meta_path: Optional[Path],
    brief_path: Path,
    brief_meta_path: Path,
    strategy_path: Path,
    strategy_meta_path: Path,
    trace_path: Path,
    trace_meta_path: Path,
    diff_strategy_path: Path,
    diff_strategy_meta_path: Path,
    diff_trace_path: Path,
    diff_trace_meta_path: Path,
    as_of: Optional[str] = None,
    strategy_md_path: Optional[Path] = None,
    diff_strategy_md_path: Optional[Path] = None,
    diff_trace_md_path: Optional[Path] = None,
    write_report: bool = False,
) -> VerificationResult:
    manifest_bytes = manifest_path.read_bytes()
    manifest = _load_json(manifest_path, "Manifest")
    _require_keys(manifest, ["schema_version", "as_of", "inputs_hash", "artifacts"], "manifest")
    if manifest.get("schema_version") != 1:
        raise VerifyManifestNoDataError("Manifest schema_version must be 1.")
    manifest_as_of = str(manifest.get("as_of", ""))
    _check_date(manifest_as_of, "Manifest as_of")

    artifacts = manifest.get("artifacts", {})
    if not isinstance(artifacts, dict):
        raise VerifyManifestNoDataError("Manifest artifacts must be object.")
    _require_keys(
        artifacts,
        [
            "brief",
            "strategy",
            "trace_strategy_brief",
            "diff_strategy_brief",
            "diff_trace_strategy_brief",
            "markdown",
        ],
        "manifest.artifacts",
    )

    if as_of:
        _check_date(as_of, "Requested as_of")
        if as_of != manifest_as_of:
            raise VerifyManifestNoDataError("Manifest as_of does not match requested as_of.")

    meta: Optional[Dict[str, Any]] = None
    if manifest_meta_path is not None:
        meta = _load_json(manifest_meta_path, "Manifest meta")
        _require_keys(
            meta,
            [
                "schema_version",
                "adapter_version",
                "inputs",
                "inputs_hash",
                "normalized_manifest_hash",
                "rows",
                "cache_hit",
            ],
            "manifest_meta",
        )
        if meta.get("schema_version") != 1:
            raise VerifyManifestNoDataError("Manifest meta schema_version must be 1.")
        if meta.get("adapter_version") != "audit_manifest_adapter_v1":
            raise VerifyManifestIntegrityError("Manifest meta adapter_version mismatch.")
        manifest_hash = sha256_hex(manifest_bytes)
        if meta.get("normalized_manifest_hash") != manifest_hash:
            raise VerifyManifestIntegrityError("Manifest hash mismatch.")
        if meta.get("inputs_hash") != manifest.get("inputs_hash"):
            raise VerifyManifestIntegrityError("Manifest inputs_hash mismatch.")
        if meta.get("inputs") != artifacts:
            raise VerifyManifestIntegrityError("Manifest meta inputs mismatch.")

    brief = _load_json(brief_path, "Brief")
    _require_keys(brief, ["as_of"], "brief")
    _check_date(str(brief.get("as_of", "")), "Brief as_of")

    strategy = _load_json(strategy_path, "Strategy")
    _require_keys(strategy, ["as_of", "signals", "playbook"], "strategy")
    _check_date(str(strategy.get("as_of", "")), "Strategy as_of")

    trace = _load_json(trace_path, "Trace")
    _require_keys(trace, ["as_of", "inputs_hash", "artifacts"], "trace")
    _check_date(str(trace.get("as_of", "")), "Trace as_of")

    diff_strategy = _load_json(diff_strategy_path, "Strategy diff")
    _require_keys(diff_strategy, ["left", "right", "inputs_hash"], "strategy_diff")
    diff_trace = _load_json(diff_trace_path, "Trace diff")
    _require_keys(diff_trace, ["left", "right", "inputs_hash"], "trace_diff")

    for label, payload in [("Strategy diff", diff_strategy), ("Trace diff", diff_trace)]:
        for side in ("left", "right"):
            if "as_of" not in payload.get(side, {}):
                raise VerifyManifestNoDataError(f"{label} missing {side}.as_of")
            _check_date(str(payload[side].get("as_of", "")), f"{label} {side}.as_of")

    if brief.get("as_of") != manifest_as_of:
        raise VerifyManifestNoDataError("Brief as_of does not match manifest as_of.")
    if strategy.get("as_of") != manifest_as_of:
        raise VerifyManifestNoDataError("Strategy as_of does not match manifest as_of.")
    if trace.get("as_of") != manifest_as_of:
        raise VerifyManifestNoDataError("Trace as_of does not match manifest as_of.")
    if diff_strategy["left"].get("as_of") != diff_strategy["right"].get("as_of"):
        raise VerifyManifestNoDataError("Strategy diff as_of mismatch between left and right.")
    if diff_trace["left"].get("as_of") != diff_trace["right"].get("as_of"):
        raise VerifyManifestNoDataError("Trace diff as_of mismatch between left and right.")
    if diff_strategy["left"].get("as_of") != manifest_as_of:
        raise VerifyManifestNoDataError("Strategy diff as_of does not match manifest as_of.")
    if diff_trace["left"].get("as_of") != manifest_as_of:
        raise VerifyManifestNoDataError("Trace diff as_of does not match manifest as_of.")

    brief_meta = _load_json(brief_meta_path, "Brief meta")
    _require_keys(
        brief_meta,
        ["normalized_brief_hash", "inputs_hash", "inputs"],
        "brief_meta",
    )
    brief_hash = sha256_hex(brief_path.read_bytes())
    if brief_meta.get("normalized_brief_hash") != brief_hash:
        raise VerifyManifestIntegrityError("Brief hash mismatch.")

    strategy_meta = _load_json(strategy_meta_path, "Strategy meta")
    _require_keys(
        strategy_meta,
        ["normalized_strategy_hash", "inputs_hash", "markdown_hash", "inputs"],
        "strategy_meta",
    )
    strategy_hash = sha256_hex(strategy_path.read_bytes())
    if strategy_meta.get("normalized_strategy_hash") != strategy_hash:
        raise VerifyManifestIntegrityError("Strategy hash mismatch.")

    trace_meta = _load_json(trace_meta_path, "Trace meta")
    _require_keys(
        trace_meta,
        ["normalized_trace_hash", "inputs_hash", "inputs"],
        "trace_meta",
    )
    trace_hash = sha256_hex(trace_path.read_bytes())
    if trace_meta.get("normalized_trace_hash") != trace_hash:
        raise VerifyManifestIntegrityError("Trace hash mismatch.")

    diff_strategy_meta = _load_json(diff_strategy_meta_path, "Strategy diff meta")
    _require_keys(
        diff_strategy_meta,
        ["normalized_diff_hash", "inputs_hash", "inputs"],
        "strategy_diff_meta",
    )
    diff_strategy_hash = sha256_hex(diff_strategy_path.read_bytes())
    if diff_strategy_meta.get("normalized_diff_hash") != diff_strategy_hash:
        raise VerifyManifestIntegrityError("Strategy diff hash mismatch.")

    diff_trace_meta = _load_json(diff_trace_meta_path, "Trace diff meta")
    _require_keys(
        diff_trace_meta,
        ["normalized_diff_hash", "inputs_hash", "inputs"],
        "trace_diff_meta",
    )
    diff_trace_hash = sha256_hex(diff_trace_path.read_bytes())
    if diff_trace_meta.get("normalized_diff_hash") != diff_trace_hash:
        raise VerifyManifestIntegrityError("Trace diff hash mismatch.")

    brief_inputs_hash_value = brief_inputs_hash(
        manifest_as_of,
        brief_meta["inputs"]["prices"]["normalized_csv_hash"],
        brief_meta["inputs"]["filings"]["normalized_jsonl_hash"],
        brief_meta["inputs"]["catalysts"]["normalized_jsonl_hash"],
    )
    _check_inputs_hash(
        "brief",
        brief_inputs_hash_value,
        brief_meta.get("inputs_hash"),
        mismatch_message="Brief inputs_hash mismatch.",
    )

    strategy_inputs_hash_value = strategy_inputs_hash(
        manifest_as_of,
        strategy_meta["inputs"]["brief"]["normalized_brief_hash"],
        strategy_meta["inputs"]["earnings"]["normalized_jsonl_hash"],
        strategy_meta["inputs"]["catalysts"]["normalized_jsonl_hash"],
    )
    _check_inputs_hash(
        "strategy",
        strategy_inputs_hash_value,
        strategy_meta.get("inputs_hash"),
        mismatch_message="Strategy inputs_hash mismatch.",
    )

    trace_inputs_hash_value = trace_inputs_hash(
        manifest_as_of,
        trace_meta["inputs"]["brief"]["normalized_brief_hash"],
        trace_meta["inputs"]["earnings"]["normalized_jsonl_hash"],
        trace_meta["inputs"]["catalysts"]["normalized_jsonl_hash"],
        trace_meta["inputs"]["strategy"]["normalized_strategy_hash"],
        trace_meta["inputs"]["markdown"]["markdown_hash"],
    )
    _check_inputs_hash(
        "trace",
        trace_inputs_hash_value,
        trace_meta.get("inputs_hash"),
        mismatch_message="Trace inputs_hash mismatch.",
    )

    diff_strategy_inputs_hash_value = strategy_diff_inputs_hash(
        left_as_of=diff_strategy["left"]["as_of"],
        left_inputs_hash=diff_strategy["left"]["inputs_hash"],
        left_strategy_hash=diff_strategy["left"]["normalized_strategy_hash"],
        left_markdown_hash=diff_strategy["left"]["markdown_hash"],
        right_as_of=diff_strategy["right"]["as_of"],
        right_inputs_hash=diff_strategy["right"]["inputs_hash"],
        right_strategy_hash=diff_strategy["right"]["normalized_strategy_hash"],
        right_markdown_hash=diff_strategy["right"]["markdown_hash"],
    )
    _check_inputs_hash(
        "strategy_diff",
        diff_strategy_inputs_hash_value,
        diff_strategy_meta.get("inputs_hash"),
        mismatch_message="Strategy diff inputs_hash mismatch.",
    )

    diff_trace_inputs_hash_value = trace_diff_inputs_hash(
        left_as_of=diff_trace["left"]["as_of"],
        left_inputs_hash=diff_trace["left"]["inputs_hash"],
        left_trace_hash=diff_trace["left"]["normalized_trace_hash"],
        left_markdown_hash=diff_trace["left"]["artifacts"]["markdown"]["markdown_hash"],
        right_as_of=diff_trace["right"]["as_of"],
        right_inputs_hash=diff_trace["right"]["inputs_hash"],
        right_trace_hash=diff_trace["right"]["normalized_trace_hash"],
        right_markdown_hash=diff_trace["right"]["artifacts"]["markdown"]["markdown_hash"],
    )
    _check_inputs_hash(
        "trace_diff",
        diff_trace_inputs_hash_value,
        diff_trace_meta.get("inputs_hash"),
        mismatch_message="Trace diff inputs_hash mismatch.",
    )

    artifacts_manifest = manifest["artifacts"]
    _check_inputs_hash(
        "manifest",
        brief_hash,
        artifacts_manifest["brief"]["normalized_brief_hash"],
        mismatch_message="Manifest brief hash mismatch.",
    )
    _check_inputs_hash(
        "manifest",
        brief_inputs_hash_value,
        artifacts_manifest["brief"]["inputs_hash"],
        mismatch_message="Manifest brief inputs_hash mismatch.",
    )
    _check_inputs_hash(
        "manifest",
        strategy_hash,
        artifacts_manifest["strategy"]["normalized_strategy_hash"],
        mismatch_message="Manifest strategy hash mismatch.",
    )
    _check_inputs_hash(
        "manifest",
        strategy_inputs_hash_value,
        artifacts_manifest["strategy"]["inputs_hash"],
        mismatch_message="Manifest strategy inputs_hash mismatch.",
    )
    _check_inputs_hash(
        "manifest",
        trace_hash,
        artifacts_manifest["trace_strategy_brief"]["normalized_trace_hash"],
        mismatch_message="Manifest trace hash mismatch.",
    )
    _check_inputs_hash(
        "manifest",
        trace_inputs_hash_value,
        artifacts_manifest["trace_strategy_brief"]["inputs_hash"],
        mismatch_message="Manifest trace inputs_hash mismatch.",
    )
    _check_inputs_hash(
        "manifest",
        diff_strategy_hash,
        artifacts_manifest["diff_strategy_brief"]["normalized_diff_hash"],
        mismatch_message="Manifest diff strategy hash mismatch.",
    )
    _check_inputs_hash(
        "manifest",
        diff_strategy_inputs_hash_value,
        artifacts_manifest["diff_strategy_brief"]["inputs_hash"],
        mismatch_message="Manifest diff strategy inputs_hash mismatch.",
    )
    _check_inputs_hash(
        "manifest",
        diff_trace_hash,
        artifacts_manifest["diff_trace_strategy_brief"]["normalized_diff_hash"],
        mismatch_message="Manifest diff trace hash mismatch.",
    )
    _check_inputs_hash(
        "manifest",
        diff_trace_inputs_hash_value,
        artifacts_manifest["diff_trace_strategy_brief"]["inputs_hash"],
        mismatch_message="Manifest diff trace inputs_hash mismatch.",
    )

    strategy_markdown_hash = strategy_meta.get("markdown_hash")
    if artifacts_manifest["strategy"]["markdown_hash"] != strategy_markdown_hash:
        raise VerifyManifestIntegrityError("Manifest strategy markdown hash mismatch.")
    if strategy_md_path:
        md_hash = sha256_hex(strategy_md_path.read_bytes())
        if md_hash != artifacts_manifest["strategy"]["markdown_hash"]:
            raise VerifyManifestIntegrityError("Strategy markdown hash mismatch.")

    if diff_strategy_md_path:
        md_hash = sha256_hex(diff_strategy_md_path.read_bytes())
        if md_hash != artifacts_manifest["markdown"]["brief_strategy_diff_md_hash"]:
            raise VerifyManifestIntegrityError("Diff strategy markdown hash mismatch.")

    if diff_trace_md_path:
        md_hash = sha256_hex(diff_trace_md_path.read_bytes())
        if md_hash != artifacts_manifest["markdown"]["trace_strategy_diff_md_hash"]:
            raise VerifyManifestIntegrityError("Diff trace markdown hash mismatch.")

    inputs_digest = manifest_inputs_hash(
        as_of=manifest_as_of,
        brief_hash=brief_hash,
        brief_inputs_hash_value=brief_inputs_hash_value,
        strategy_hash=strategy_hash,
        strategy_inputs_hash_value=strategy_inputs_hash_value,
        strategy_markdown_hash=strategy_markdown_hash,
        trace_hash=trace_hash,
        trace_inputs_hash_value=trace_inputs_hash_value,
        diff_strategy_hash=diff_strategy_hash,
        diff_strategy_inputs_hash_value=diff_strategy_inputs_hash_value,
        diff_trace_hash=diff_trace_hash,
        diff_trace_inputs_hash_value=diff_trace_inputs_hash_value,
        diff_strategy_md_hash=artifacts_manifest["markdown"]["brief_strategy_diff_md_hash"],
        diff_trace_md_hash=artifacts_manifest["markdown"]["trace_strategy_diff_md_hash"],
    )
    if manifest.get("inputs_hash") != inputs_digest:
        raise VerifyManifestIntegrityError("Manifest inputs_hash mismatch.")
    if meta and meta.get("inputs_hash") != inputs_digest:
        raise VerifyManifestIntegrityError("Manifest meta inputs_hash mismatch.")

    report = None
    if write_report:
        checks = [
            {"name": "manifest_hash", "ok": True},
            {"name": "manifest_inputs_hash", "ok": True},
            {"name": "brief_hash", "ok": True},
            {"name": "brief_inputs_hash", "ok": True},
            {"name": "strategy_hash", "ok": True},
            {"name": "strategy_inputs_hash", "ok": True},
            {"name": "trace_hash", "ok": True},
            {"name": "trace_inputs_hash", "ok": True},
            {"name": "diff_strategy_hash", "ok": True},
            {"name": "diff_strategy_inputs_hash", "ok": True},
            {"name": "diff_trace_hash", "ok": True},
            {"name": "diff_trace_inputs_hash", "ok": True},
            {"name": "as_of_coherence", "ok": True},
        ]
        report = {
            "schema_version": 1,
            "as_of": manifest_as_of,
            "inputs_hash": inputs_digest,
            "checks": checks,
        }

    return VerificationResult(report=report)
