from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from pathlib import Path

from core.regime.bundle_manifest import expected_bundle_entries


def _env() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    return env


def _paths() -> dict[str, Path]:
    return {
        "manifest": Path("tests/fixtures/audit_manifest_aapl_2024-02-15.json"),
        "manifest_meta": Path("tests/fixtures/audit_manifest_aapl_2024-02-15.meta.json"),
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
        "strategy_md": Path("tests/fixtures/brief_strategy_diff_same_aapl_2024-02-15.md"),
        "diff_strategy_md": Path("tests/fixtures/brief_strategy_diff_same_aapl_2024-02-15.md"),
        "diff_trace_md": Path(
            "tests/fixtures/strategy_brief_trace_diff_same_aapl_2024-02-15.md"
        ),
    }


def _run_bundle(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    out_path = tmp_path / "bundle.zip"
    paths = _paths()
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "bundle-manifest",
        "--manifest",
        str(paths["manifest"]),
        "--manifest-meta",
        str(paths["manifest_meta"]),
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
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr
    return out_path


def test_bundle_manifest_deterministic_bytes(tmp_path: Path):
    out_a = _run_bundle(tmp_path / "a")
    out_b = _run_bundle(tmp_path / "b")
    assert out_a.read_bytes() == out_b.read_bytes()


def test_bundle_manifest_entries(tmp_path: Path):
    out_path = _run_bundle(tmp_path)
    with zipfile.ZipFile(out_path, "r") as zf:
        names = zf.namelist()
    expected = expected_bundle_entries(
        strategy_md=None,
        diff_strategy_md=Path("tests/fixtures/brief_strategy_diff_same_aapl_2024-02-15.md"),
        diff_trace_md=Path("tests/fixtures/strategy_brief_trace_diff_same_aapl_2024-02-15.md"),
    )
    assert names == expected


def test_bundle_manifest_hash_mismatch_exit_4(tmp_path: Path):
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
        "bundle-manifest",
        "--manifest",
        str(paths["manifest"]),
        "--manifest-meta",
        str(paths["manifest_meta"]),
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
        str(tmp_path / "bundle.zip"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 4
    assert "brief hash mismatch" in result.stderr.lower()
