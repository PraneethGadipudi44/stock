from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from core.regime.filings_adapter import cache_paths, tickers_cache_path


def _env() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    return env


def _write_cached_tickers(cache_dir: Path) -> None:
    path = tickers_cache_path(cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = Path("tests/fixtures/edgar_company_tickers.json").read_bytes()
    path.write_bytes(raw)


def _write_cached_submissions(
    cache_dir: Path,
    ticker: str,
    start: str,
    end: str,
    cik_padded: str,
    raw: bytes,
) -> Path:
    paths = cache_paths(cache_dir, ticker, start, end, cik_padded)
    paths.raw.parent.mkdir(parents=True, exist_ok=True)
    paths.raw.write_bytes(raw)
    return paths.raw


def test_ingest_filings_deterministic_bytes(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    _write_cached_tickers(cache_dir)
    raw = Path("tests/fixtures/edgar_submissions_AAPL.json").read_bytes()
    _write_cached_submissions(cache_dir, "AAPL", "2024-02-01", "2024-03-01", "0000320193", raw)

    out_a = tmp_path / "a.jsonl"
    meta_a = tmp_path / "a.meta.json"
    out_b = tmp_path / "b.jsonl"
    meta_b = tmp_path / "b.meta.json"

    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "ingest-filings",
        "--ticker",
        "AAPL",
        "--start",
        "2024-02-01",
        "--end",
        "2024-03-01",
        "--out",
        str(out_a),
        "--meta-out",
        str(meta_a),
        "--cache-dir",
        str(cache_dir),
        "--cache-only",
        "--user-agent",
        "eds-regime/1.0 (dev@example.com)",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr

    cmd[cmd.index(str(out_a))] = str(out_b)
    cmd[cmd.index(str(meta_a))] = str(meta_b)
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr

    assert out_a.read_bytes() == out_b.read_bytes()
    assert meta_a.read_bytes() == meta_b.read_bytes()


def test_ingest_filings_output_matches_fixture(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    _write_cached_tickers(cache_dir)
    raw = Path("tests/fixtures/edgar_submissions_AAPL.json").read_bytes()
    _write_cached_submissions(cache_dir, "AAPL", "2024-02-01", "2024-03-01", "0000320193", raw)

    out_path = tmp_path / "filings.jsonl"
    meta_path = tmp_path / "filings.meta.json"
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "ingest-filings",
        "--ticker",
        "AAPL",
        "--start",
        "2024-02-01",
        "--end",
        "2024-03-01",
        "--out",
        str(out_path),
        "--meta-out",
        str(meta_path),
        "--cache-dir",
        str(cache_dir),
        "--cache-only",
        "--user-agent",
        "eds-regime/1.0 (dev@example.com)",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr

    expected = Path("tests/fixtures/edgar_aapl_2024-02-01_2024-03-01.jsonl").read_text(
        encoding="utf-8"
    ).replace("\r\n", "\n")
    actual = out_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not expected.endswith("\n"):
        expected += "\n"
    assert actual == expected

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["provider"] == "edgar"
    assert meta["ticker"] == "AAPL"
    assert meta["cik"] == "0000320193"
    assert meta["rows"] == 2


def test_ingest_filings_missing_user_agent_exit_2(tmp_path: Path):
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "ingest-filings",
        "--ticker",
        "AAPL",
        "--start",
        "2024-02-01",
        "--end",
        "2024-03-01",
        "--out",
        str(tmp_path / "out.jsonl"),
        "--cache-only",
        "--cache-dir",
        str(tmp_path / "cache"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 2
    assert "user-agent" in result.stderr.lower()


def test_ingest_filings_empty_results_exit_3(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    _write_cached_tickers(cache_dir)
    raw = Path("tests/fixtures/edgar_submissions_AAPL.json").read_bytes()
    _write_cached_submissions(cache_dir, "AAPL", "2024-04-01", "2024-04-05", "0000320193", raw)

    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "ingest-filings",
        "--ticker",
        "AAPL",
        "--start",
        "2024-04-01",
        "--end",
        "2024-04-05",
        "--out",
        str(tmp_path / "out.jsonl"),
        "--cache-dir",
        str(cache_dir),
        "--cache-only",
        "--user-agent",
        "eds-regime/1.0 (dev@example.com)",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 3
    assert "No filings" in result.stderr


def test_ingest_filings_provider_error_exit_4(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    _write_cached_tickers(cache_dir)
    _write_cached_submissions(
        cache_dir,
        "AAPL",
        "2024-02-01",
        "2024-03-01",
        "0000320193",
        b"not-json",
    )

    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "ingest-filings",
        "--ticker",
        "AAPL",
        "--start",
        "2024-02-01",
        "--end",
        "2024-03-01",
        "--out",
        str(tmp_path / "out.jsonl"),
        "--cache-dir",
        str(cache_dir),
        "--cache-only",
        "--user-agent",
        "eds-regime/1.0 (dev@example.com)",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 4
    assert "Provider response is not valid JSON" in result.stderr


def test_ingest_filings_cache_corruption_exit_4(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    _write_cached_tickers(cache_dir)
    raw = Path("tests/fixtures/edgar_submissions_AAPL.json").read_bytes()
    _write_cached_submissions(cache_dir, "AAPL", "2024-02-01", "2024-03-01", "0000320193", raw)
    paths = cache_paths(cache_dir, "AAPL", "2024-02-01", "2024-03-01", "0000320193")

    bad_meta = {
        "schema_version": 1,
        "provider": "edgar",
        "provider_version": "submissions+archives_v1",
        "adapter_version": "filings_adapter_v1",
        "ticker": "AAPL",
        "cik": "0000320193",
        "start": "2024-02-01",
        "end": "2024-03-01",
        "forms": ["10-K", "10-Q", "8-K"],
        "request_canonical": paths.request_canonical,
        "cache_key": paths.cache_key,
        "rows": 2,
        "source_hash": "0" * 64,
        "normalized_jsonl_hash": "0" * 64,
        "cache_hit": True,
    }
    paths.meta.write_text(json.dumps(bad_meta), encoding="utf-8")

    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "ingest-filings",
        "--ticker",
        "AAPL",
        "--start",
        "2024-02-01",
        "--end",
        "2024-03-01",
        "--out",
        str(tmp_path / "out.jsonl"),
        "--cache-dir",
        str(cache_dir),
        "--cache-only",
        "--user-agent",
        "eds-regime/1.0 (dev@example.com)",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 4
    assert "cache corruption" in result.stderr.lower()
