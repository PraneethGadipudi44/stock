from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from core.regime.store import JsonlSnapshotStore


def _load_snapshot(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_store_append_latest_history_get(tmp_path: Path):
    fixture_path = Path("tests/fixtures/regime_snapshot_golden.json")
    snapshot = _load_snapshot(fixture_path)

    store = JsonlSnapshotStore(tmp_path, cfg_path=Path("config/regime_v1.yaml"))
    snapshot_json = json.dumps(snapshot, sort_keys=True)
    snapshot_id = store.append(snapshot_json)

    assert snapshot_id == snapshot["snapshot_id"]

    latest = store.latest()
    assert latest is not None
    assert latest["snapshot"]["snapshot_id"] == snapshot_id
    assert latest["metadata"]["inputs_hash"]
    assert latest["metadata"]["config_hash"]

    schema_path = Path("contracts/regime_store_entry.schema.v1.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    snapshot_schema = json.loads(
        Path("contracts/regime_snapshot.schema.json").read_text(encoding="utf-8")
    )
    base_uri = Path("contracts").resolve().as_uri() + "/"
    schema["$id"] = base_uri + "regime_store_entry.schema.v1.json"
    snapshot_schema["$id"] = base_uri + "regime_snapshot.schema.v1.json"
    resolver = jsonschema.RefResolver.from_schema(
        schema,
        store={
            schema["$id"]: schema,
            snapshot_schema["$id"]: snapshot_schema,
        },
    )
    jsonschema.validate(latest, schema, resolver=resolver)

    got = store.get(snapshot_id)
    assert got is not None
    assert got["snapshot"]["snapshot_id"] == snapshot_id

    history = store.history(limit=10)
    assert len(history) == 1
    assert history[0]["snapshot"]["snapshot_id"] == snapshot_id


def test_store_history_ordering(tmp_path: Path):
    fixture_path = Path("tests/fixtures/regime_snapshot_golden.json")
    snapshot = _load_snapshot(fixture_path)

    snapshot_b = dict(snapshot)
    snapshot_b["snapshot_id"] = "b" * 32
    snapshot_b["as_of_ts"] = "2026-02-06T13:30:00Z"

    store = JsonlSnapshotStore(tmp_path)
    store.append(json.dumps(snapshot, sort_keys=True))
    store.append(json.dumps(snapshot_b, sort_keys=True))

    history = store.history(limit=10)
    assert history[-1]["snapshot"]["snapshot_id"] == snapshot_b["snapshot_id"]
    assert history[0]["snapshot"]["snapshot_id"] == snapshot["snapshot_id"]
