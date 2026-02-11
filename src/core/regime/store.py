from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .models import parse_as_of_ts
from .resources import read_text


class SnapshotStore(ABC):
    """Persistence interface for regime snapshots."""

    @abstractmethod
    def append(self, snapshot_json: str) -> str:
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

    def append(self, snapshot_json: str) -> str:
        snapshot = json.loads(snapshot_json)
        snapshot_id = snapshot.get("snapshot_id")
        if not snapshot_id:
            raise ValueError("snapshot_id is required in snapshot JSON.")

        as_of_ts = snapshot.get("as_of_ts")
        if not as_of_ts:
            raise ValueError("as_of_ts is required in snapshot JSON.")

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

        line = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        with open(partition, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")

        self._write_latest(entry)
        return snapshot_id

    def latest(self) -> Optional[Dict[str, Any]]:
        if not self.latest_path.exists():
            return None
        with open(self.latest_path, "r", encoding="utf-8") as handle:
            return json.load(handle)

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
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    yield json.loads(line)

    def _write_latest(self, entry: Dict[str, Any]) -> None:
        temp_path = self.latest_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(entry, handle, sort_keys=True, indent=2)
        temp_path.replace(self.latest_path)


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
