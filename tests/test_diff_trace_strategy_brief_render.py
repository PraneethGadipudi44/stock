from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


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


def _run_diff(tmp_path: Path, cache_dir: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    md_path = tmp_path / "diff.md"
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
        "--render-md",
        str(md_path),
        "--cache-dir",
        str(cache_dir),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr
    return md_path


def test_diff_trace_strategy_brief_render_deterministic_bytes(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    md_a = _run_diff(tmp_path / "a", cache_dir)
    md_b = _run_diff(tmp_path / "b", cache_dir)
    assert md_a.read_bytes() == md_b.read_bytes()


def test_diff_trace_strategy_brief_render_matches_fixture(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    md_path = _run_diff(tmp_path, cache_dir)
    expected = Path(
        "tests/fixtures/strategy_brief_trace_diff_same_aapl_2024-02-15.md"
    ).read_text(encoding="utf-8").replace("\r\n", "\n")
    actual = md_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert actual == expected
