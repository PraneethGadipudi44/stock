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
        "brief": Path("tests/fixtures/brief_aapl_2024-02-15.json"),
        "brief_meta": Path("tests/fixtures/brief_aapl_2024-02-15.meta.json"),
        "earnings": Path("tests/fixtures/earnings_aapl_2024-02-01_2024-03-01.jsonl"),
        "earnings_meta": Path(
            "tests/fixtures/earnings_aapl_2024-02-01_2024-03-01.meta.json"
        ),
        "catalysts": Path(
            "tests/fixtures/catalysts_aapl_2024-02-01_2024-03-01.jsonl"
        ),
        "catalysts_meta": Path(
            "tests/fixtures/catalysts_aapl_2024-02-01_2024-03-01.meta.json"
        ),
        "strategy": Path("tests/fixtures/brief_strategy_aapl_2024-02-15.json"),
        "strategy_meta": Path("tests/fixtures/brief_strategy_aapl_2024-02-15.meta.json"),
    }


def _run_trace(tmp_path: Path, cache_dir: Path) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    out_path = tmp_path / "trace.json"
    meta_path = tmp_path / "trace.meta.json"
    paths = _paths()
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "trace-strategy-brief",
        "--as-of",
        "2024-02-15",
        "--brief",
        str(paths["brief"]),
        "--brief-meta",
        str(paths["brief_meta"]),
        "--earnings",
        str(paths["earnings"]),
        "--earnings-meta",
        str(paths["earnings_meta"]),
        "--catalysts",
        str(paths["catalysts"]),
        "--catalysts-meta",
        str(paths["catalysts_meta"]),
        "--strategy",
        str(paths["strategy"]),
        "--strategy-meta",
        str(paths["strategy_meta"]),
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


def test_trace_strategy_brief_deterministic_bytes(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    out_a, meta_a = _run_trace(tmp_path / "a", cache_dir)
    out_b, meta_b = _run_trace(tmp_path / "b", cache_dir)
    assert out_a.read_bytes() == out_b.read_bytes()
    assert meta_a.read_bytes() == meta_b.read_bytes()


def test_trace_strategy_brief_matches_fixture(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    out_path, meta_path = _run_trace(tmp_path, cache_dir)

    expected = Path(
        "tests/fixtures/strategy_brief_trace_aapl_2024-02-15.json"
    ).read_text(encoding="utf-8").replace("\r\n", "\n")
    actual = out_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not expected.endswith("\n"):
        expected += "\n"
    if not actual.endswith("\n"):
        actual += "\n"
    assert actual == expected

    expected_meta = Path(
        "tests/fixtures/strategy_brief_trace_aapl_2024-02-15.meta.json"
    ).read_text(encoding="utf-8").replace("\r\n", "\n")
    actual_meta = meta_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not expected_meta.endswith("\n"):
        expected_meta += "\n"
    if not actual_meta.endswith("\n"):
        actual_meta += "\n"
    assert actual_meta == expected_meta


def test_trace_strategy_brief_hash_mismatch_exit_4(tmp_path: Path):
    paths = _paths()
    tampered_strategy = tmp_path / "strategy.json"
    tampered_strategy.write_text(
        paths["strategy"].read_text(encoding="utf-8").replace("AAPL", "AAPX"),
        encoding="utf-8",
    )
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "trace-strategy-brief",
        "--as-of",
        "2024-02-15",
        "--brief",
        str(paths["brief"]),
        "--brief-meta",
        str(paths["brief_meta"]),
        "--earnings",
        str(paths["earnings"]),
        "--earnings-meta",
        str(paths["earnings_meta"]),
        "--catalysts",
        str(paths["catalysts"]),
        "--catalysts-meta",
        str(paths["catalysts_meta"]),
        "--strategy",
        str(tampered_strategy),
        "--strategy-meta",
        str(paths["strategy_meta"]),
        "--out",
        str(tmp_path / "trace.json"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 4
    assert "strategy hash mismatch" in result.stderr.lower()


def test_trace_strategy_brief_asof_mismatch_exit_3(tmp_path: Path):
    paths = _paths()
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "trace-strategy-brief",
        "--as-of",
        "2024-02-16",
        "--brief",
        str(paths["brief"]),
        "--brief-meta",
        str(paths["brief_meta"]),
        "--earnings",
        str(paths["earnings"]),
        "--earnings-meta",
        str(paths["earnings_meta"]),
        "--catalysts",
        str(paths["catalysts"]),
        "--catalysts-meta",
        str(paths["catalysts_meta"]),
        "--strategy",
        str(paths["strategy"]),
        "--strategy-meta",
        str(paths["strategy_meta"]),
        "--out",
        str(tmp_path / "trace.json"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 3
    assert "strategy as_of" in result.stderr.lower()
