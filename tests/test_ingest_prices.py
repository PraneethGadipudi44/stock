from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from core.regime.prices_adapter import cache_paths, sha256_hex


def _env() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    env.pop("POLYGON_API_KEY", None)
    return env


def _write_cached_raw(cache_dir: Path, symbol: str, start: str, end: str, raw: bytes) -> None:
    paths = cache_paths(cache_dir, symbol, start, end)
    paths.raw.parent.mkdir(parents=True, exist_ok=True)
    paths.raw.write_bytes(raw)


def test_ingest_prices_deterministic_bytes(tmp_path: Path):
    symbol = "SPY"
    start = "2026-01-16"
    end = "2026-01-21"
    raw = Path("tests/fixtures/polygon_spy_2026-01-16_2026-01-21.json").read_bytes()

    cache_dir = tmp_path / "cache"
    _write_cached_raw(cache_dir, symbol, start, end, raw)

    out_a = tmp_path / "a.csv"
    meta_a = tmp_path / "a.meta.json"
    out_b = tmp_path / "b.csv"
    meta_b = tmp_path / "b.meta.json"

    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "ingest-prices",
        "--symbol",
        symbol,
        "--start",
        start,
        "--end",
        end,
        "--out",
        str(out_a),
        "--meta-out",
        str(meta_a),
        "--cache-dir",
        str(cache_dir),
        "--cache-only",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr

    cmd[cmd.index(str(out_a))] = str(out_b)
    cmd[cmd.index(str(meta_a))] = str(meta_b)
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr

    assert out_a.read_bytes() == out_b.read_bytes()
    assert meta_a.read_bytes() == meta_b.read_bytes()


def test_ingest_prices_output_matches_fixture(tmp_path: Path):
    symbol = "SPY"
    start = "2026-01-16"
    end = "2026-01-21"
    raw = Path("tests/fixtures/polygon_spy_2026-01-16_2026-01-21.json").read_bytes()

    cache_dir = tmp_path / "cache"
    _write_cached_raw(cache_dir, symbol, start, end, raw)

    out_path = tmp_path / "prices.csv"
    meta_path = tmp_path / "prices.meta.json"
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "ingest-prices",
        "--symbol",
        symbol,
        "--start",
        start,
        "--end",
        end,
        "--out",
        str(out_path),
        "--meta-out",
        str(meta_path),
        "--cache-dir",
        str(cache_dir),
        "--cache-only",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr

    expected = Path("tests/fixtures/polygon_spy_2026-01-16_2026-01-21.csv").read_text(
        encoding="utf-8"
    ).replace("\r\n", "\n")
    if not expected.endswith("\n"):
        expected += "\n"
    actual = out_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert actual == expected

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    paths = cache_paths(cache_dir, symbol, start, end)
    assert meta["request_canonical"] == paths.request_canonical
    assert meta["cache_key"] == paths.cache_key
    assert meta["date_semantics"] == "end_inclusive"
    assert meta["rounding_mode"] == "HALF_UP"
    assert meta["adapter_version"] == "prices_adapter_v1"
    assert meta["provider"] == "polygon"
    assert meta["rows"] == 3
    assert meta["cache_hit"] is True
    assert meta["normalized_csv_hash"] == sha256_hex(actual.encode("utf-8"))


def test_ingest_prices_cache_only_miss_fails(tmp_path: Path):
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "ingest-prices",
        "--symbol",
        "SPY",
        "--start",
        "2026-01-16",
        "--end",
        "2026-01-21",
        "--out",
        str(tmp_path / "prices.csv"),
        "--cache-dir",
        str(tmp_path / "cache"),
        "--cache-only",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 4
    assert "cache-only" in result.stderr.lower()


def test_ingest_prices_bad_date_exit_2(tmp_path: Path):
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "ingest-prices",
        "--symbol",
        "SPY",
        "--start",
        "2026-01-21",
        "--end",
        "2026-01-16",
        "--out",
        str(tmp_path / "prices.csv"),
        "--cache-dir",
        str(tmp_path / "cache"),
        "--cache-only",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 2
    assert "Start date must be <= end date" in result.stderr


def test_ingest_prices_empty_results_exit_3(tmp_path: Path):
    symbol = "SPY"
    start = "2026-01-16"
    end = "2026-01-21"
    cache_dir = tmp_path / "cache"

    empty_payload = json.dumps({"results": []}).encode("utf-8")
    _write_cached_raw(cache_dir, symbol, start, end, empty_payload)

    out_path = tmp_path / "prices.csv"
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "ingest-prices",
        "--symbol",
        symbol,
        "--start",
        start,
        "--end",
        end,
        "--out",
        str(out_path),
        "--cache-dir",
        str(cache_dir),
        "--cache-only",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 3
    assert "No data" in result.stderr


def test_ingest_prices_cache_corruption_detected(tmp_path: Path):
    symbol = "SPY"
    start = "2026-01-16"
    end = "2026-01-21"
    raw = Path("tests/fixtures/polygon_spy_2026-01-16_2026-01-21.json").read_bytes()
    cache_dir = tmp_path / "cache"
    _write_cached_raw(cache_dir, symbol, start, end, raw)
    paths = cache_paths(cache_dir, symbol, start, end)

    bad_meta = {
        "schema_version": 1,
        "provider": "polygon",
        "provider_version": "v2",
        "adapter_version": "prices_adapter_v1",
        "endpoint": paths.endpoint,
        "request_canonical": paths.request_canonical,
        "cache_key": paths.cache_key,
        "symbol": symbol,
        "start": start,
        "end": end,
        "date_semantics": "end_inclusive",
        "rounding_mode": "HALF_UP",
        "rows": 3,
        "source_hash": "0" * 64,
        "normalized_csv_hash": "0" * 64,
        "cache_hit": True,
    }
    paths.meta.write_text(json.dumps(bad_meta), encoding="utf-8")

    out_path = tmp_path / "prices.csv"
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "ingest-prices",
        "--symbol",
        symbol,
        "--start",
        start,
        "--end",
        end,
        "--out",
        str(out_path),
        "--cache-dir",
        str(cache_dir),
        "--cache-only",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 4
    assert "cache corruption" in result.stderr.lower()
