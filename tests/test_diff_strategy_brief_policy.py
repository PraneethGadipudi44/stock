from __future__ import annotations

import json
import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict

from core.regime.brief_strategy_diff_adapter import inputs_hash as diff_inputs_hash


def _env() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    return env


def _paths() -> dict[str, Path]:
    return {
        "left_strategy": Path("tests/fixtures/brief_strategy_aapl_2024-02-15.json"),
        "left_meta": Path("tests/fixtures/brief_strategy_aapl_2024-02-15.meta.json"),
        "right_strategy": Path("tests/fixtures/brief_strategy_aapl_2024-02-15.json"),
        "right_meta": Path("tests/fixtures/brief_strategy_aapl_2024-02-15.meta.json"),
    }


def _run_diff(tmp_path: Path, cache_dir: Path) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    out_path = tmp_path / "diff.json"
    meta_path = tmp_path / "diff.meta.json"
    paths = _paths()
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "diff-strategy-brief",
        "--left-strategy",
        str(paths["left_strategy"]),
        "--left-meta",
        str(paths["left_meta"]),
        "--right-strategy",
        str(paths["right_strategy"]),
        "--right-meta",
        str(paths["right_meta"]),
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


def test_diff_inputs_hash_matches_recompute(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    out_path, meta_path = _run_diff(tmp_path, cache_dir)
    diff_payload = _load_json(out_path)
    meta = _load_json(meta_path)

    left = diff_payload["left"]
    right = diff_payload["right"]
    expected = diff_inputs_hash(
        left_as_of=left["as_of"],
        left_inputs_hash=left["inputs_hash"],
        left_strategy_hash=left["normalized_strategy_hash"],
        left_markdown_hash=left["markdown_hash"],
        right_as_of=right["as_of"],
        right_inputs_hash=right["inputs_hash"],
        right_strategy_hash=right["normalized_strategy_hash"],
        right_markdown_hash=right["markdown_hash"],
    )
    assert diff_payload["inputs_hash"] == expected
    assert meta["inputs_hash"] == expected


def test_diff_normalized_hash_matches_bytes(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    out_path, meta_path = _run_diff(tmp_path, cache_dir)
    meta = _load_json(meta_path)
    diff_bytes = out_path.read_bytes()
    assert meta["normalized_diff_hash"] == sha256(diff_bytes).hexdigest()


def test_diff_meta_inputs_match_payload(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    out_path, meta_path = _run_diff(tmp_path, cache_dir)
    diff_payload = _load_json(out_path)
    meta = _load_json(meta_path)

    assert (
        meta["inputs"]["left"]["normalized_strategy_hash"]
        == diff_payload["left"]["normalized_strategy_hash"]
    )
    assert meta["inputs"]["left"]["inputs_hash"] == diff_payload["left"]["inputs_hash"]
    assert meta["inputs"]["left"]["markdown_hash"] == diff_payload["left"]["markdown_hash"]
    assert (
        meta["inputs"]["right"]["normalized_strategy_hash"]
        == diff_payload["right"]["normalized_strategy_hash"]
    )
    assert meta["inputs"]["right"]["inputs_hash"] == diff_payload["right"]["inputs_hash"]
    assert (
        meta["inputs"]["right"]["markdown_hash"] == diff_payload["right"]["markdown_hash"]
    )


def test_diff_is_hash_only(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    out_path, _ = _run_diff(tmp_path, cache_dir)
    diff_payload = _load_json(out_path)

    assert set(diff_payload.keys()) == {
        "schema_version",
        "left",
        "right",
        "inputs_hash",
        "changes",
        "coverage_delta",
        "summary",
    }

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
    _collect_keys(diff_payload, collected)
    assert forbidden.isdisjoint(collected)
