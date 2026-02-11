from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .models import parse_as_of_ts
from .resources import read_text


class StoreIntegrityError(ValueError):
    """Raised when store contents are invalid or corrupted."""


class SnapshotStore(ABC):
    """Persistence interface for regime snapshots."""

    @abstractmethod
    def append(self, snapshot_json: str, no_clobber: bool = False) -> str:
        """Append a snapshot JSON string, returning the snapshot_id."""
        raise NotImplementedError

    @abstractmethod
    def latest(self) -> Optional[Dict[str, Any]]:
        """Return the latest stored entry, or None."""
        raise NotImplementedError

    @abstractmethod
    def get(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Return a stored entry by snapshot_id, or None."""
        raise NotImplementedError

    @abstractmethod
    def history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return recent stored entries, newest last."""
        raise NotImplementedError


@dataclass
class JsonlSnapshotStore(SnapshotStore):
    """Append-only JSONL snapshot store with an atomic latest pointer."""

    root_dir: Path
    cfg_path: Optional[Path] = None

    def __post_init__(self) -> None:
        self.root_dir = Path(self.root_dir)
        self.data_dir = self.root_dir / "data"
        self.latest_path = self.root_dir / "latest.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.cfg_path:
            self.config_hash = _hash_file(self.cfg_path)
        else:
            self.config_hash = _hash_text(read_text("regime_v1.yaml"))

    def append(self, snapshot_json: str, no_clobber: bool = False) -> str:
        try:
            snapshot = json.loads(snapshot_json)
        except json.JSONDecodeError as exc:
            raise StoreIntegrityError(f"Snapshot JSON is invalid: {exc.msg}") from exc
        _validate_snapshot(snapshot)
        snapshot_id = snapshot.get("snapshot_id")
        if not snapshot_id:
            raise StoreIntegrityError("snapshot_id is required in snapshot JSON.")

        existing = self.get(snapshot_id)
        if existing is not None:
            if no_clobber:
                raise StoreIntegrityError(f"Snapshot {snapshot_id} already exists.")
            self._write_latest(existing)
            return snapshot_id

        as_of_ts = snapshot.get("as_of_ts")
        if not as_of_ts:
            raise StoreIntegrityError("as_of_ts is required in snapshot JSON.")

        partition = _partition_path(self.data_dir, as_of_ts)
        partition.parent.mkdir(parents=True, exist_ok=True)

        inputs_hash = snapshot.get("inputs_hash") or _hash_inputs(snapshot)
        entry = {
            "snapshot": snapshot,
            "metadata": {
                "stored_at": _utc_now_iso(),
                "config_hash": self.config_hash,
                "inputs_hash": inputs_hash,
            },
        }
        _validate_store_entry(entry)

        line = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        with open(partition, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())

        self._write_latest(entry)
        return snapshot_id

    def latest(self) -> Optional[Dict[str, Any]]:
        if not self.latest_path.exists():
            return None
        try:
            with open(self.latest_path, "r", encoding="utf-8") as handle:
                entry = json.load(handle)
        except json.JSONDecodeError as exc:
            raise StoreIntegrityError(
                f"Invalid JSON in latest.json: {exc.msg}"
            ) from exc
        _validate_store_entry(entry)
        return entry

    def get(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        for entry in self._iter_entries():
            if entry.get("snapshot", {}).get("snapshot_id") == snapshot_id:
                return entry
        return None

    def history(self, limit: int = 100) -> List[Dict[str, Any]]:
        entries = list(self._iter_entries())
        entries.sort(
            key=lambda entry: (
                parse_as_of_ts(entry["snapshot"]["as_of_ts"]),
                entry["snapshot"]["snapshot_id"],
            )
        )
        if limit <= 0:
            return []
        return entries[-limit:]

    def _iter_entries(self) -> Iterable[Dict[str, Any]]:
        if not self.data_dir.exists():
            return []
        files = sorted(self.data_dir.rglob("*.jsonl"))
        for path in files:
            with open(path, "r", encoding="utf-8") as handle:
                for line_no, line in enumerate(handle, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise StoreIntegrityError(
                            f"Invalid JSON in {path}:{line_no}: {exc.msg}"
                        ) from exc
                    _validate_store_entry(entry)
                    yield entry

    def _write_latest(self, entry: Dict[str, Any]) -> None:
        _atomic_write_json(self.latest_path, entry)

    def validate(self) -> Dict[str, Any]:
        summary = {
            "entries": 0,
            "errors": 0,
            "duplicate_ids": 0,
            "first_error": None,
        }
        if not self.data_dir.exists():
            return summary
        seen = set()
        files = sorted(self.data_dir.rglob("*.jsonl"))
        for path in files:
            with open(path, "r", encoding="utf-8") as handle:
                for line_no, line in enumerate(handle, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    summary["entries"] += 1
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError as exc:
                        summary["errors"] += 1
                        summary["first_error"] = (
                            f"Invalid JSON in {path}:{line_no}: {exc.msg}"
                        )
                        return summary
                    try:
                        _validate_store_entry(entry)
                    except StoreIntegrityError as exc:
                        summary["errors"] += 1
                        summary["first_error"] = str(exc)
                        return summary
                    snapshot_id = entry["snapshot"]["snapshot_id"]
                    if snapshot_id in seen:
                        summary["errors"] += 1
                        summary["duplicate_ids"] += 1
                        summary["first_error"] = (
                            f"Duplicate snapshot_id detected: {snapshot_id}"
                        )
                        return summary
                    seen.add(snapshot_id)
        return summary


def _partition_path(root: Path, as_of_ts: str) -> Path:
    as_of = parse_as_of_ts(as_of_ts)
    return root / f"{as_of.year:04d}" / f"{as_of.month:02d}" / "regime.jsonl"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _hash_file(path: Optional[Path]) -> Optional[str]:
    if path is None:
        return None
    data = Path(path).read_bytes()
    return sha256(data).hexdigest()


def _hash_inputs(snapshot: Dict[str, Any]) -> str:
    payload = {
        "as_of_ts": snapshot.get("as_of_ts"),
        "session": snapshot.get("session"),
        "engine_version": snapshot.get("engine_version"),
        "universe": snapshot.get("universe"),
        "benchmarks": snapshot.get("benchmarks"),
        "reasoning": snapshot.get("reasoning"),
        "metrics_snapshot": snapshot.get("metrics_snapshot"),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


def _hash_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    temp_path = path.with_name(path.name + ".tmp")
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)


@lru_cache(maxsize=1)
def _snapshot_schema() -> Dict[str, Any]:
    return json.loads(read_text("regime_snapshot.schema.json"))


@lru_cache(maxsize=1)
def _store_entry_schema() -> Dict[str, Any]:
    return json.loads(read_text("regime_store_entry.schema.v1.json"))


def _schema_version_expected() -> int:
    schema = _snapshot_schema()
    version = schema.get("properties", {}).get("schema_version", {}).get("const")
    if version is None:
        raise StoreIntegrityError("Snapshot schema missing schema_version const.")
    if not isinstance(version, int):
        raise StoreIntegrityError("Snapshot schema_version const must be integer.")
    return version


def _validate_snapshot(snapshot: Dict[str, Any]) -> None:
    if not isinstance(snapshot, dict):
        raise StoreIntegrityError("Snapshot must be a JSON object.")
    schema = _snapshot_schema()
    required = set(schema.get("required", []))
    missing = required - set(snapshot.keys())
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise StoreIntegrityError(f"Missing required snapshot fields: {missing_list}")
    expected_version = _schema_version_expected()
    actual_version = snapshot.get("schema_version")
    if actual_version != expected_version:
        raise StoreIntegrityError(
            f"Unsupported schema_version: {actual_version} (expected {expected_version})."
        )


def _validate_store_entry(entry: Dict[str, Any]) -> None:
    if not isinstance(entry, dict):
        raise StoreIntegrityError("Store entry must be a JSON object.")
    schema = _store_entry_schema()
    required = set(schema.get("required", []))
    missing = required - set(entry.keys())
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise StoreIntegrityError(f"Missing required store fields: {missing_list}")

    snapshot = entry.get("snapshot")
    metadata = entry.get("metadata")
    if not isinstance(snapshot, dict):
        raise StoreIntegrityError("Store entry snapshot must be a JSON object.")
    if not isinstance(metadata, dict):
        raise StoreIntegrityError("Store entry metadata must be a JSON object.")

    meta_required = set(
        schema.get("properties", {}).get("metadata", {}).get("required", [])
    )
    meta_missing = meta_required - set(metadata.keys())
    if meta_missing:
        missing_list = ", ".join(sorted(meta_missing))
        raise StoreIntegrityError(
            f"Missing required metadata fields: {missing_list}"
        )

    if not isinstance(metadata.get("stored_at"), str):
        raise StoreIntegrityError("metadata.stored_at must be a string.")
    if not isinstance(metadata.get("inputs_hash"), str):
        raise StoreIntegrityError("metadata.inputs_hash must be a string.")
    config_hash = metadata.get("config_hash")
    if config_hash is not None and not isinstance(config_hash, str):
        raise StoreIntegrityError("metadata.config_hash must be a string or null.")

    _validate_snapshot(snapshot)
