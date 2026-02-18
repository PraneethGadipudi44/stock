from __future__ import annotations

import json
import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

from core.regime.strategy_brief_trace_adapter import (
    inputs_hash as trace_inputs_hash,
)

def _env() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    return env


def _paths() -> dict[str, Path]:
    return {
        "left_trace": Path("tests/fixtures/strategy_brief_trace_aapl_2024-02-15.json"),
        "left_trace_meta": Path(
            "tests/fixtures/strategy_brief_trace_aapl_2024-02-15.meta.json"
        ),
        "right_trace": Path("tests/fixtures/strategy_brief_trace_aapl_2024-02-15.json"),
        "right_trace_meta": Path(
            "tests/fixtures/strategy_brief_trace_aapl_2024-02-15.meta.json"
        ),
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
        "diff-trace-strategy-brief",
        "--left-trace",
        str(paths["left_trace"]),
        "--left-trace-meta",
        str(paths["left_trace_meta"]),
        "--right-trace",
        str(paths["right_trace"]),
        "--right-trace-meta",
        str(paths["right_trace_meta"]),
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


def test_diff_trace_strategy_brief_deterministic_bytes(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    out_a, meta_a = _run_diff(tmp_path / "a", cache_dir)
    out_b, meta_b = _run_diff(tmp_path / "b", cache_dir)
    assert out_a.read_bytes() == out_b.read_bytes()
    assert meta_a.read_bytes() == meta_b.read_bytes()


def test_diff_trace_strategy_brief_matches_fixture(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    out_path, meta_path = _run_diff(tmp_path, cache_dir)

    expected = Path(
        "tests/fixtures/strategy_brief_trace_diff_same_aapl_2024-02-15.json"
    ).read_text(encoding="utf-8").replace("\r\n", "\n")
    actual = out_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not expected.endswith("\n"):
        expected += "\n"
    if not actual.endswith("\n"):
        actual += "\n"
    assert actual == expected

    expected_meta = Path(
        "tests/fixtures/strategy_brief_trace_diff_same_aapl_2024-02-15.meta.json"
    ).read_text(encoding="utf-8").replace("\r\n", "\n")
    actual_meta = meta_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not expected_meta.endswith("\n"):
        expected_meta += "\n"
    if not actual_meta.endswith("\n"):
        actual_meta += "\n"
    assert actual_meta == expected_meta


def test_diff_trace_strategy_brief_hash_mismatch_exit_4(tmp_path: Path):
    paths = _paths()
    tampered_left = tmp_path / "left.json"
    tampered_left.write_text(
        paths["left_trace"].read_text(encoding="utf-8").replace("AAPL", "AAPX"),
        encoding="utf-8",
    )
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "diff-trace-strategy-brief",
        "--left-trace",
        str(tampered_left),
        "--left-trace-meta",
        str(paths["left_trace_meta"]),
        "--right-trace",
        str(paths["right_trace"]),
        "--right-trace-meta",
        str(paths["right_trace_meta"]),
        "--out",
        str(tmp_path / "diff.json"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 4
    assert "left trace hash mismatch" in result.stderr.lower()


def test_diff_trace_strategy_brief_cache_only_miss_exit_4(tmp_path: Path):
    paths = _paths()
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "diff-trace-strategy-brief",
        "--left-trace",
        str(paths["left_trace"]),
        "--left-trace-meta",
        str(paths["left_trace_meta"]),
        "--right-trace",
        str(paths["right_trace"]),
        "--right-trace-meta",
        str(paths["right_trace_meta"]),
        "--out",
        str(tmp_path / "diff.json"),
        "--cache-dir",
        str(tmp_path / "cache"),
        "--cache-only",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 4
    assert "cache miss" in result.stderr.lower()


def test_diff_trace_strategy_brief_asof_mismatch_exit_3(tmp_path: Path):
    paths = _paths()
    tampered_right = tmp_path / "right.json"
    right_payload = json.loads(paths["right_trace"].read_text(encoding="utf-8"))
    right_payload["as_of"] = "2024-02-16"
    artifacts = right_payload["artifacts"]
    right_payload["inputs_hash"] = trace_inputs_hash(
        right_payload["as_of"],
        artifacts["brief"]["normalized_brief_hash"],
        artifacts["earnings"]["normalized_jsonl_hash"],
        artifacts["catalysts"]["normalized_jsonl_hash"],
        artifacts["strategy"]["normalized_strategy_hash"],
        artifacts["markdown"]["markdown_hash"],
    )
    tampered_right.write_text(
        json.dumps(right_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    tampered_meta = tmp_path / "right.meta.json"
    right_meta = json.loads(paths["right_trace_meta"].read_text(encoding="utf-8"))
    right_meta["inputs_hash"] = right_payload["inputs_hash"]
    right_meta["normalized_trace_hash"] = sha256(tampered_right.read_bytes()).hexdigest()
    tampered_meta.write_text(
        json.dumps(right_meta, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "diff-trace-strategy-brief",
        "--left-trace",
        str(paths["left_trace"]),
        "--left-trace-meta",
        str(paths["left_trace_meta"]),
        "--right-trace",
        str(tampered_right),
        "--right-trace-meta",
        str(tampered_meta),
        "--out",
        str(tmp_path / "diff.json"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 3
    assert "as_of mismatch" in result.stderr.lower()
