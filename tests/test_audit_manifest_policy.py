from __future__ import annotations

import json
import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict

from core.regime.audit_manifest_adapter import inputs_hash as manifest_inputs_hash


def _env() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    return env


def _paths() -> dict[str, Path]:
    return {
        "brief": Path("tests/fixtures/brief_aapl_2024-02-15.json"),
        "brief_meta": Path("tests/fixtures/brief_aapl_2024-02-15.meta.json"),
        "strategy": Path("tests/fixtures/brief_strategy_aapl_2024-02-15.json"),
        "strategy_meta": Path("tests/fixtures/brief_strategy_aapl_2024-02-15.meta.json"),
        "trace": Path("tests/fixtures/strategy_brief_trace_aapl_2024-02-15.json"),
        "trace_meta": Path("tests/fixtures/strategy_brief_trace_aapl_2024-02-15.meta.json"),
        "diff_strategy": Path(
            "tests/fixtures/brief_strategy_diff_same_aapl_2024-02-15.json"
        ),
        "diff_strategy_meta": Path(
            "tests/fixtures/brief_strategy_diff_same_aapl_2024-02-15.meta.json"
        ),
        "diff_trace": Path(
            "tests/fixtures/strategy_brief_trace_diff_same_aapl_2024-02-15.json"
        ),
        "diff_trace_meta": Path(
            "tests/fixtures/strategy_brief_trace_diff_same_aapl_2024-02-15.meta.json"
        ),
        "diff_strategy_md": Path(
            "tests/fixtures/brief_strategy_diff_same_aapl_2024-02-15.md"
        ),
        "diff_trace_md": Path(
            "tests/fixtures/strategy_brief_trace_diff_same_aapl_2024-02-15.md"
        ),
    }


def _run_manifest(tmp_path: Path, cache_dir: Path) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    out_path = tmp_path / "manifest.json"
    meta_path = tmp_path / "manifest.meta.json"
    paths = _paths()
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "audit-manifest",
        "--as-of",
        "2024-02-15",
        "--brief",
        str(paths["brief"]),
        "--brief-meta",
        str(paths["brief_meta"]),
        "--strategy",
        str(paths["strategy"]),
        "--strategy-meta",
        str(paths["strategy_meta"]),
        "--trace",
        str(paths["trace"]),
        "--trace-meta",
        str(paths["trace_meta"]),
        "--diff-strategy",
        str(paths["diff_strategy"]),
        "--diff-strategy-meta",
        str(paths["diff_strategy_meta"]),
        "--diff-trace",
        str(paths["diff_trace"]),
        "--diff-trace-meta",
        str(paths["diff_trace_meta"]),
        "--diff-strategy-md",
        str(paths["diff_strategy_md"]),
        "--diff-trace-md",
        str(paths["diff_trace_md"]),
        "--out",
        str(out_path),
        "--meta-out",
        str(meta_path),
        "--cache-dir",
        str(cache_dir),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr
    return out_path, meta_path


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _collect_keys(payload: Any, keys: set[str]) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            keys.add(key)
            _collect_keys(value, keys)
    elif isinstance(payload, list):
        for item in payload:
            _collect_keys(item, keys)


def test_manifest_inputs_hash_matches_recompute(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    out_path, meta_path = _run_manifest(tmp_path, cache_dir)
    manifest = _load_json(out_path)
    meta = _load_json(meta_path)

    artifacts = manifest["artifacts"]
    expected = manifest_inputs_hash(
        as_of=manifest["as_of"],
        brief_hash=artifacts["brief"]["normalized_brief_hash"],
        brief_inputs_hash_value=artifacts["brief"]["inputs_hash"],
        strategy_hash=artifacts["strategy"]["normalized_strategy_hash"],
        strategy_inputs_hash_value=artifacts["strategy"]["inputs_hash"],
        strategy_markdown_hash=artifacts["strategy"]["markdown_hash"],
        trace_hash=artifacts["trace_strategy_brief"]["normalized_trace_hash"],
        trace_inputs_hash_value=artifacts["trace_strategy_brief"]["inputs_hash"],
        diff_strategy_hash=artifacts["diff_strategy_brief"]["normalized_diff_hash"],
        diff_strategy_inputs_hash_value=artifacts["diff_strategy_brief"]["inputs_hash"],
        diff_trace_hash=artifacts["diff_trace_strategy_brief"]["normalized_diff_hash"],
        diff_trace_inputs_hash_value=artifacts["diff_trace_strategy_brief"]["inputs_hash"],
        diff_strategy_md_hash=artifacts["markdown"]["brief_strategy_diff_md_hash"],
        diff_trace_md_hash=artifacts["markdown"]["trace_strategy_diff_md_hash"],
    )
    assert manifest["inputs_hash"] == expected
    assert meta["inputs_hash"] == expected


def test_manifest_normalized_hash_matches_bytes(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    out_path, meta_path = _run_manifest(tmp_path, cache_dir)
    meta = _load_json(meta_path)
    manifest_bytes = out_path.read_bytes()
    assert meta["normalized_manifest_hash"] == sha256(manifest_bytes).hexdigest()


def test_manifest_meta_inputs_match_payload(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    out_path, meta_path = _run_manifest(tmp_path, cache_dir)
    manifest = _load_json(out_path)
    meta = _load_json(meta_path)

    assert meta["inputs"] == manifest["artifacts"]
    assert meta["rows"]["artifact_count"] == len(manifest["artifacts"]) == 6


def test_manifest_is_hash_only(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    out_path, _ = _run_manifest(tmp_path, cache_dir)
    manifest = _load_json(out_path)

    assert set(manifest.keys()) == {"schema_version", "as_of", "inputs_hash", "artifacts"}
    forbidden = {
        "signals",
        "playbook",
        "focus_list",
        "today_catalysts",
        "recent_catalysts",
        "price_moves",
        "ticker",
    }
    collected: set[str] = set()
    _collect_keys(manifest, collected)
    assert forbidden.isdisjoint(collected)
