from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from core.regime.store import JsonlSnapshotStore, StoreIntegrityError


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


def test_store_atomic_latest_write(tmp_path: Path):
    fixture_path = Path("tests/fixtures/regime_snapshot_golden.json")
    snapshot = _load_snapshot(fixture_path)
    snapshot_b = dict(snapshot)
    snapshot_b["snapshot_id"] = "b" * 32
    snapshot_b["as_of_ts"] = "2026-02-06T13:30:00Z"

    store = JsonlSnapshotStore(tmp_path)
    store.append(json.dumps(snapshot, sort_keys=True))
    json.loads(store.latest_path.read_text(encoding="utf-8"))

    store.append(json.dumps(snapshot_b, sort_keys=True))
    json.loads(store.latest_path.read_text(encoding="utf-8"))


def test_store_rejects_unknown_schema_version(tmp_path: Path):
    fixture_path = Path("tests/fixtures/regime_snapshot_golden.json")
    snapshot = _load_snapshot(fixture_path)
    snapshot["schema_version"] = 2
    entry = {
        "snapshot": snapshot,
        "metadata": {
            "stored_at": "2026-02-05T13:30:00Z",
            "inputs_hash": "inputs",
            "config_hash": None,
        },
    }
    store = JsonlSnapshotStore(tmp_path)
    store.latest_path.write_text(json.dumps(entry, sort_keys=True), encoding="utf-8")

    try:
        store.latest()
        assert False, "Expected StoreIntegrityError"
    except StoreIntegrityError as exc:
        assert "schema_version" in str(exc)


def test_store_rejects_missing_required_fields(tmp_path: Path):
    fixture_path = Path("tests/fixtures/regime_snapshot_golden.json")
    snapshot = _load_snapshot(fixture_path)
    snapshot.pop("snapshot_id", None)
    entry = {
        "snapshot": snapshot,
        "metadata": {
            "stored_at": "2026-02-05T13:30:00Z",
            "inputs_hash": "inputs",
            "config_hash": None,
        },
    }
    store = JsonlSnapshotStore(tmp_path)
    store.latest_path.write_text(json.dumps(entry, sort_keys=True), encoding="utf-8")

    try:
        store.latest()
        assert False, "Expected StoreIntegrityError"
    except StoreIntegrityError as exc:
        assert "snapshot_id" in str(exc)


def test_store_append_existing_id_is_noop(tmp_path: Path):
    fixture_path = Path("tests/fixtures/regime_snapshot_golden.json")
    snapshot = _load_snapshot(fixture_path)
    store = JsonlSnapshotStore(tmp_path)
    snapshot_json = json.dumps(snapshot, sort_keys=True)
    store.append(snapshot_json)

    partition = store.data_dir / "2026" / "02" / "regime.jsonl"
    before_lines = partition.read_text(encoding="utf-8").strip().splitlines()

    store.append(snapshot_json)
    after_lines = partition.read_text(encoding="utf-8").strip().splitlines()

    assert len(before_lines) == len(after_lines) == 1


def test_store_no_clobber_existing_id_fails(tmp_path: Path):
    fixture_path = Path("tests/fixtures/regime_snapshot_golden.json")
    snapshot = _load_snapshot(fixture_path)
    store = JsonlSnapshotStore(tmp_path)
    snapshot_json = json.dumps(snapshot, sort_keys=True)
    store.append(snapshot_json)

    try:
        store.append(snapshot_json, no_clobber=True)
        assert False, "Expected StoreIntegrityError"
    except StoreIntegrityError as exc:
        assert "already exists" in str(exc)


def test_store_validate_reports_first_error_deterministically(tmp_path: Path):
    fixture_path = Path("tests/fixtures/regime_snapshot_golden.json")
    snapshot = _load_snapshot(fixture_path)
    store = JsonlSnapshotStore(tmp_path)
    store.append(json.dumps(snapshot, sort_keys=True))

    partition = store.data_dir / "2026" / "02" / "regime.jsonl"
    with open(partition, "a", encoding="utf-8") as handle:
        handle.write("not-json\n")

    summary = store.validate()
    assert summary["errors"] == 1
    assert "Invalid JSON" in summary["first_error"]
