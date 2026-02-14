from __future__ import annotations

import json
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
        "prices": Path("tests/fixtures/prices_aapl_2024-02-01_2024-03-01.csv"),
        "prices_meta": Path(
            "tests/fixtures/prices_aapl_2024-02-01_2024-03-01.meta.json"
        ),
        "filings": Path("tests/fixtures/edgar_aapl_2024-02-01_2024-03-01.jsonl"),
        "filings_meta": Path(
            "tests/fixtures/edgar_aapl_2024-02-01_2024-03-01.meta.json"
        ),
        "catalysts": Path(
            "tests/fixtures/catalysts_aapl_2024-02-01_2024-03-01.jsonl"
        ),
        "catalysts_meta": Path("tests/fixtures/catalysts_aapl_2024-02-01_2024-03-01.meta.json"),
    }


def _run_brief(tmp_path: Path, cache_dir: Path) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    out_path = tmp_path / "brief.json"
    meta_path = tmp_path / "brief.meta.json"
    paths = _paths()
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "brief",
        "--as-of",
        "2024-02-15",
        "--prices",
        str(paths["prices"]),
        "--prices-meta",
        str(paths["prices_meta"]),
        "--filings",
        str(paths["filings"]),
        "--filings-meta",
        str(paths["filings_meta"]),
        "--catalysts",
        str(paths["catalysts"]),
        "--catalysts-meta",
        str(paths["catalysts_meta"]),
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


def test_brief_deterministic_bytes(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    out_a, meta_a = _run_brief(tmp_path / "a", cache_dir)
    out_b, meta_b = _run_brief(tmp_path / "b", cache_dir)
    assert out_a.read_bytes() == out_b.read_bytes()
    assert meta_a.read_bytes() == meta_b.read_bytes()


def test_brief_output_matches_fixture(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    out_path, meta_path = _run_brief(tmp_path, cache_dir)

    expected = Path("tests/fixtures/brief_aapl_2024-02-15.json").read_text(
        encoding="utf-8"
    ).replace("\r\n", "\n")
    actual = out_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not expected.endswith("\n"):
        expected += "\n"
    if not actual.endswith("\n"):
        actual += "\n"
    assert actual == expected

    expected_meta = Path("tests/fixtures/brief_aapl_2024-02-15.meta.json").read_text(
        encoding="utf-8"
    ).replace("\r\n", "\n")
    actual_meta = meta_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not expected_meta.endswith("\n"):
        expected_meta += "\n"
    if not actual_meta.endswith("\n"):
        actual_meta += "\n"
    assert actual_meta == expected_meta


def test_brief_hash_mismatch_exit_4(tmp_path: Path):
    paths = _paths()
    tampered_prices = tmp_path / "prices.csv"
    tampered_prices.write_text(
        paths["prices"].read_text(encoding="utf-8").replace("189.34", "189.35"),
        encoding="utf-8",
    )

    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "brief",
        "--as-of",
        "2024-02-15",
        "--prices",
        str(tampered_prices),
        "--prices-meta",
        str(paths["prices_meta"]),
        "--filings",
        str(paths["filings"]),
        "--filings-meta",
        str(paths["filings_meta"]),
        "--catalysts",
        str(paths["catalysts"]),
        "--catalysts-meta",
        str(paths["catalysts_meta"]),
        "--out",
        str(tmp_path / "brief.json"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 4
    assert "prices hash mismatch" in result.stderr.lower()


def test_brief_empty_catalysts_ok(tmp_path: Path):
    paths = _paths()
    empty_catalysts = tmp_path / "empty.jsonl"
    empty_catalysts.write_text("", encoding="utf-8")
    empty_meta = tmp_path / "empty.meta.json"
    empty_meta.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "adapter_version": "catalysts_adapter_v1",
                "inputs": {
                    "prices": {
                        "source_hash": "0" * 64,
                        "normalized_csv_hash": "0" * 64,
                        "request_canonical": "fixture",
                        "cache_key": "fixture",
                    },
                    "filings": {
                        "source_hash": "0" * 64,
                        "normalized_jsonl_hash": "0" * 64,
                        "request_canonical": "fixture",
                        "cache_key": "fixture",
                    },
                    "catalysts": {"normalized_jsonl_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
                },
                "inputs_hash": "0" * 64,
                "normalized_jsonl_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "rows": 0,
                "cache_hit": True,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "brief",
        "--as-of",
        "2024-02-15",
        "--prices",
        str(paths["prices"]),
        "--prices-meta",
        str(paths["prices_meta"]),
        "--filings",
        str(paths["filings"]),
        "--filings-meta",
        str(paths["filings_meta"]),
        "--catalysts",
        str(empty_catalysts),
        "--catalysts-meta",
        str(empty_meta),
        "--out",
        str(tmp_path / "brief.json"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr


def test_brief_no_prices_exit_3(tmp_path: Path):
    paths = _paths()
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "brief",
        "--as-of",
        "2024-01-01",
        "--prices",
        str(paths["prices"]),
        "--prices-meta",
        str(paths["prices_meta"]),
        "--filings",
        str(paths["filings"]),
        "--filings-meta",
        str(paths["filings_meta"]),
        "--catalysts",
        str(paths["catalysts"]),
        "--catalysts-meta",
        str(paths["catalysts_meta"]),
        "--out",
        str(tmp_path / "brief.json"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 3
    assert "No prices" in result.stderr
