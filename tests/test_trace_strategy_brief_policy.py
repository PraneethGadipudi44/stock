from __future__ import annotations

import json
import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict

from core.regime.brief_strategy_adapter import render_markdown
from core.regime.strategy_brief_trace_adapter import inputs_hash as trace_inputs_hash
from core.regime.strategy_brief_trace_adapter import strategy_coverage


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


def _run_trace(
    tmp_path: Path,
    cache_dir: Path,
    *,
    as_of: str = "2024-02-15",
    markdown: Path | None = None,
    extra: list[str] | None = None,
) -> tuple[Path, Path]:
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
        as_of,
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
    if markdown is not None:
        cmd.extend(["--markdown", str(markdown)])
    if extra:
        cmd.extend(extra)
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr
    return out_path, meta_path


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _collect_keys(payload: Any, keys: set[str]) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            keys.add(key)
            _collect_keys(value, keys)
    elif isinstance(payload, list):
        for item in payload:
            _collect_keys(item, keys)


def test_trace_inputs_hash_matches_recompute(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    out_path, meta_path = _run_trace(tmp_path, cache_dir)
    trace = _load_json(out_path)
    meta = _load_json(meta_path)

    artifacts = trace["artifacts"]
    markdown_hash = artifacts["markdown"]["markdown_hash"]
    expected_inputs_hash = trace_inputs_hash(
        trace["as_of"],
        artifacts["brief"]["normalized_brief_hash"],
        artifacts["earnings"]["normalized_jsonl_hash"],
        artifacts["catalysts"]["normalized_jsonl_hash"],
        artifacts["strategy"]["normalized_strategy_hash"],
        markdown_hash,
    )
    assert trace["inputs_hash"] == expected_inputs_hash
    assert meta["inputs_hash"] == expected_inputs_hash


def test_trace_meta_hashes_match_artifacts(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    out_path, meta_path = _run_trace(tmp_path, cache_dir)
    trace = _load_json(out_path)
    meta = _load_json(meta_path)

    assert meta["inputs"]["brief"]["normalized_brief_hash"] == trace["artifacts"]["brief"]["normalized_brief_hash"]
    assert meta["inputs"]["earnings"]["normalized_jsonl_hash"] == trace["artifacts"]["earnings"]["normalized_jsonl_hash"]
    assert meta["inputs"]["catalysts"]["normalized_jsonl_hash"] == trace["artifacts"]["catalysts"]["normalized_jsonl_hash"]
    assert meta["inputs"]["strategy"]["normalized_strategy_hash"] == trace["artifacts"]["strategy"]["normalized_strategy_hash"]
    assert meta["inputs"]["markdown"]["markdown_hash"] == trace["artifacts"]["markdown"]["markdown_hash"]


def test_trace_normalized_hash_matches_bytes(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    out_path, meta_path = _run_trace(tmp_path, cache_dir)
    meta = _load_json(meta_path)
    trace_bytes = out_path.read_bytes()
    assert meta["normalized_trace_hash"] == sha256(trace_bytes).hexdigest()


def test_trace_coverage_matches_strategy(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    out_path, meta_path = _run_trace(tmp_path, cache_dir)
    trace = _load_json(out_path)
    meta = _load_json(meta_path)

    strategy = _load_json(Path("tests/fixtures/brief_strategy_aapl_2024-02-15.json"))
    expected_coverage = strategy_coverage(strategy)
    assert trace["coverage"] == expected_coverage
    assert meta["rows"] == expected_coverage


def test_trace_is_hash_only(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    out_path, _ = _run_trace(tmp_path, cache_dir)
    trace = _load_json(out_path)

    assert set(trace.keys()) == {"schema_version", "as_of", "inputs_hash", "artifacts", "coverage"}
    assert set(trace["artifacts"].keys()) == {"brief", "earnings", "catalysts", "strategy", "markdown"}

    forbidden_keys = {
        "signals",
        "playbook",
        "focus_list",
        "today_catalysts",
        "recent_catalysts",
        "price_moves",
        "summary",
        "ticker",
    }
    collected: set[str] = set()
    _collect_keys(trace, collected)
    assert forbidden_keys.isdisjoint(collected)


def test_trace_markdown_hash_behavior(tmp_path: Path):
    strategy = _load_json(Path("tests/fixtures/brief_strategy_aapl_2024-02-15.json"))
    markdown = render_markdown(strategy)
    md_path = tmp_path / "strategy.md"
    md_path.write_text(markdown, encoding="utf-8")
    expected_md_hash = sha256(md_path.read_bytes()).hexdigest()

    cache_dir = tmp_path / "cache"
    out_path, meta_path = _run_trace(tmp_path, cache_dir, markdown=md_path)
    trace = _load_json(out_path)
    meta = _load_json(meta_path)
    assert trace["artifacts"]["markdown"]["markdown_hash"] == expected_md_hash
    assert meta["inputs"]["markdown"]["markdown_hash"] == expected_md_hash


def test_trace_cache_only_miss_exit_4(tmp_path: Path):
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
        str(tmp_path / "trace.json"),
        "--cache-dir",
        str(tmp_path / "cache"),
        "--cache-only",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 4
    assert "cache miss" in result.stderr.lower()


def test_trace_refresh_deterministic_bytes_and_cache_hit(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    out_a, meta_a = _run_trace(tmp_path / "a", cache_dir)
    out_b, meta_b = _run_trace(tmp_path / "b", cache_dir, extra=["--refresh"])

    assert out_a.read_bytes() == out_b.read_bytes()
    meta_first = _load_json(meta_a)
    meta_second = _load_json(meta_b)
    assert meta_first["normalized_trace_hash"] == meta_second["normalized_trace_hash"]
    assert meta_first["inputs_hash"] == meta_second["inputs_hash"]
    assert meta_first["cache_hit"] is False
    assert meta_second["cache_hit"] is True
