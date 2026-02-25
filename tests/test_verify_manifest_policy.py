from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict


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
    }


def _run_verify(tmp_path: Path) -> Path:
    out_path = tmp_path / "report.json"
    paths = _paths()
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "verify-manifest",
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
        "--out",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr
    return out_path


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


def test_verify_manifest_report_is_hash_only(tmp_path: Path):
    report_path = _run_verify(tmp_path)
    report = _load_json(report_path)

    assert set(report.keys()) == {"schema_version", "as_of", "inputs_hash", "checks"}

    forbidden = {
        "signals",
        "playbook",
        "focus_list",
        "today_catalysts",
        "recent_catalysts",
        "price_moves",
        "ticker",
    }
    collected: set[str] = set()
    _collect_keys(report, collected)
    assert forbidden.isdisjoint(collected)
