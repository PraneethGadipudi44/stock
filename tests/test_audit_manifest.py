from __future__ import annotations

import json
import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path


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


def test_audit_manifest_deterministic_bytes(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    out_a, meta_a = _run_manifest(tmp_path / "a", cache_dir)
    out_b, meta_b = _run_manifest(tmp_path / "b", cache_dir)
    assert out_a.read_bytes() == out_b.read_bytes()
    assert meta_a.read_bytes() == meta_b.read_bytes()


def test_audit_manifest_matches_fixture(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    out_path, meta_path = _run_manifest(tmp_path, cache_dir)

    expected = Path("tests/fixtures/audit_manifest_aapl_2024-02-15.json").read_text(
        encoding="utf-8"
    ).replace("\r\n", "\n")
    actual = out_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not expected.endswith("\n"):
        expected += "\n"
    if not actual.endswith("\n"):
        actual += "\n"
    assert actual == expected

    expected_meta = Path(
        "tests/fixtures/audit_manifest_aapl_2024-02-15.meta.json"
    ).read_text(encoding="utf-8").replace("\r\n", "\n")
    actual_meta = meta_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not expected_meta.endswith("\n"):
        expected_meta += "\n"
    if not actual_meta.endswith("\n"):
        actual_meta += "\n"
    assert actual_meta == expected_meta


def test_audit_manifest_hash_mismatch_exit_4(tmp_path: Path):
    paths = _paths()
    tampered_brief = tmp_path / "brief.json"
    tampered_brief.write_text(
        paths["brief"].read_text(encoding="utf-8").replace("AAPL", "AAPX"),
        encoding="utf-8",
    )
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "audit-manifest",
        "--as-of",
        "2024-02-15",
        "--brief",
        str(tampered_brief),
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
        "--out",
        str(tmp_path / "manifest.json"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 4
    assert "brief hash mismatch" in result.stderr.lower()


def test_audit_manifest_cache_only_miss_exit_4(tmp_path: Path):
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
        "--out",
        str(tmp_path / "manifest.json"),
        "--cache-dir",
        str(tmp_path / "cache"),
        "--cache-only",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 4
    assert "cache miss" in result.stderr.lower()


def test_audit_manifest_asof_mismatch_exit_3(tmp_path: Path):
    paths = _paths()
    tampered_strategy = tmp_path / "strategy.json"
    payload = json.loads(paths["strategy"].read_text(encoding="utf-8"))
    payload["as_of"] = "2024-02-16"
    tampered_strategy.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    tampered_meta = tmp_path / "strategy.meta.json"
    meta = json.loads(paths["strategy_meta"].read_text(encoding="utf-8"))
    meta["normalized_strategy_hash"] = sha256(tampered_strategy.read_bytes()).hexdigest()
    meta["inputs_hash"] = strategy_inputs_hash(
        payload["as_of"],
        meta["inputs"]["brief"]["normalized_brief_hash"],
        meta["inputs"]["earnings"]["normalized_jsonl_hash"],
        meta["inputs"]["catalysts"]["normalized_jsonl_hash"],
    )
    tampered_meta.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")

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
        str(tampered_strategy),
        "--strategy-meta",
        str(tampered_meta),
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
        "--out",
        str(tmp_path / "manifest.json"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 3
    assert "strategy as_of" in result.stderr.lower()
from core.regime.brief_strategy_adapter import inputs_hash as strategy_inputs_hash
