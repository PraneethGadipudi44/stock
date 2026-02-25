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


def _run_manifest(tmp_path: Path) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    out_manifest = tmp_path / "manifest.json"
    out_meta = tmp_path / "manifest.meta.json"
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
        str(out_manifest),
        "--meta-out",
        str(out_meta),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr
    return out_manifest, out_meta


def test_audit_chain_smoke(tmp_path: Path):
    manifest, manifest_meta = _run_manifest(tmp_path / "manifest")
    paths = _paths()

    verify_cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "verify-manifest",
        "--manifest",
        str(manifest),
        "--manifest-meta",
        str(manifest_meta),
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
    ]
    result = subprocess.run(verify_cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr

    bundle_path = tmp_path / "bundle" / "audit_bundle.zip"
    bundle_cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "bundle-manifest",
        "--manifest",
        str(manifest),
        "--manifest-meta",
        str(manifest_meta),
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
        str(bundle_path),
    ]
    result = subprocess.run(bundle_cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr

    extract_dir = tmp_path / "bundle" / "unzipped"
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bundle_path, "r") as zf:
        names = zf.namelist()
        zf.extractall(extract_dir)
    expected = expected_bundle_entries(
        strategy_md=None,
        diff_strategy_md=paths["diff_strategy_md"],
        diff_trace_md=paths["diff_trace_md"],
    )
    assert names == expected

    verify_cmd_unzipped = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "verify-manifest",
        "--manifest",
        str(extract_dir / "manifest.json"),
        "--manifest-meta",
        str(extract_dir / "manifest.meta.json"),
        "--brief",
        str(extract_dir / "brief.json"),
        "--brief-meta",
        str(extract_dir / "brief.meta.json"),
        "--strategy",
        str(extract_dir / "strategy.json"),
        "--strategy-meta",
        str(extract_dir / "strategy.meta.json"),
        "--trace",
        str(extract_dir / "trace.json"),
        "--trace-meta",
        str(extract_dir / "trace.meta.json"),
        "--diff-strategy",
        str(extract_dir / "diff_strategy.json"),
        "--diff-strategy-meta",
        str(extract_dir / "diff_strategy.meta.json"),
        "--diff-trace",
        str(extract_dir / "diff_trace.json"),
        "--diff-trace-meta",
        str(extract_dir / "diff_trace.meta.json"),
        "--diff-strategy-md",
        str(extract_dir / "diff_strategy.md"),
        "--diff-trace-md",
        str(extract_dir / "diff_trace.md"),
    ]
    result = subprocess.run(
        verify_cmd_unzipped, capture_output=True, text=True, env=_env()
    )
    assert result.returncode == 0, result.stderr
