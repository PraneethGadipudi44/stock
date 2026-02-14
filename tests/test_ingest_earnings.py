from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from core.regime.earnings_adapter import inputs_hash


def _env() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    return env


def _paths() -> dict[str, Path]:
    return {
        "prices": Path("tests/fixtures/prices_aapl_2024-02-01_2024-03-01.csv"),
        "prices_meta": Path(
            "tests/fixtures/prices_aapl_2024-02-01_2024-03-01.meta.json"
        ),
        "filings": Path("tests/fixtures/edgar_aapl_2024-02-01_2024-03-01.jsonl"),
        "filings_meta": Path(
            "tests/fixtures/edgar_aapl_2024-02-01_2024-03-01.meta.json"
        ),
    }


def _run_ingest(tmp_path: Path, cache_dir: Path) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    out_path = tmp_path / "earnings.jsonl"
    meta_path = tmp_path / "earnings.meta.json"
    paths = _paths()
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "ingest-earnings",
        "--start",
        "2024-02-01",
        "--end",
        "2024-03-01",
        "--prices",
        str(paths["prices"]),
        "--prices-meta",
        str(paths["prices_meta"]),
        "--filings",
        str(paths["filings"]),
        "--filings-meta",
        str(paths["filings_meta"]),
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


def test_ingest_earnings_deterministic_bytes(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    out_a, meta_a = _run_ingest(tmp_path / "a", cache_dir)
    out_b, meta_b = _run_ingest(tmp_path / "b", cache_dir)
    assert out_a.read_bytes() == out_b.read_bytes()
    assert meta_a.read_bytes() == meta_b.read_bytes()


def test_ingest_earnings_output_matches_fixture(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    out_path, meta_path = _run_ingest(tmp_path, cache_dir)

    expected = Path(
        "tests/fixtures/earnings_aapl_2024-02-01_2024-03-01.jsonl"
    ).read_text(encoding="utf-8").replace("\r\n", "\n")
    actual = out_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not expected.endswith("\n"):
        expected += "\n"
    assert actual == expected

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    prices_meta = json.loads(
        Path("tests/fixtures/prices_aapl_2024-02-01_2024-03-01.meta.json").read_text(
            encoding="utf-8"
        )
    )
    filings_meta = json.loads(
        Path("tests/fixtures/edgar_aapl_2024-02-01_2024-03-01.meta.json").read_text(
            encoding="utf-8"
        )
    )
    expected_inputs_hash = inputs_hash(
        "2024-02-01",
        "2024-03-01",
        prices_meta["normalized_csv_hash"],
        filings_meta["normalized_jsonl_hash"],
    )
    assert meta["inputs_hash"] == expected_inputs_hash
    assert meta["rows"] == 1


def test_ingest_earnings_hash_mismatch_exit_4(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    paths = _paths()
    out_path = tmp_path / "earnings.jsonl"
    meta_path = tmp_path / "earnings.meta.json"

    tampered_prices = tmp_path / "prices.csv"
    tampered_prices.write_text(
        paths["prices"].read_text(encoding="utf-8").replace("189.34", "189.35"),
        encoding="utf-8",
    )

    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "ingest-earnings",
        "--start",
        "2024-02-01",
        "--end",
        "2024-03-01",
        "--prices",
        str(tampered_prices),
        "--prices-meta",
        str(paths["prices_meta"]),
        "--filings",
        str(paths["filings"]),
        "--filings-meta",
        str(paths["filings_meta"]),
        "--out",
        str(out_path),
        "--meta-out",
        str(meta_path),
        "--cache-dir",
        str(cache_dir),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 4
    assert "prices hash mismatch" in result.stderr.lower()


def test_ingest_earnings_empty_ok(tmp_path: Path):
    paths = _paths()
    empty_filings = tmp_path / "empty.jsonl"
    empty_filings.write_text("", encoding="utf-8")
    empty_meta = tmp_path / "empty.meta.json"
    empty_meta.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "provider": "edgar",
                "provider_version": "submissions+archives_v1",
                "adapter_version": "filings_adapter_v1",
                "ticker": "AAPL",
                "cik": "0000320193",
                "start": "2024-02-01",
                "end": "2024-03-01",
                "forms": ["10-K", "10-Q", "8-K"],
                "request_canonical": "fixture",
                "cache_key": "fixture",
                "rows": 0,
                "source_hash": "0" * 64,
                "normalized_jsonl_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "cache_hit": True,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    out_path = tmp_path / "earnings.jsonl"
    meta_path = tmp_path / "earnings.meta.json"

    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "ingest-earnings",
        "--start",
        "2024-02-01",
        "--end",
        "2024-03-01",
        "--prices",
        str(paths["prices"]),
        "--prices-meta",
        str(paths["prices_meta"]),
        "--filings",
        str(empty_filings),
        "--filings-meta",
        str(empty_meta),
        "--out",
        str(out_path),
        "--meta-out",
        str(meta_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr
