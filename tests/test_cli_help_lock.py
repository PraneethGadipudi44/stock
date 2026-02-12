from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _env() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    return env


def _load_fixture(name: str) -> str:
    text = Path("tests/fixtures") / name
    return text.read_text(encoding="utf-8").replace("\r\n", "\n")


def _run_help(subcmd: str) -> str:
    cmd = [sys.executable, "-m", "core.regime.cli", subcmd, "--help"]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr
    return result.stdout.replace("\r\n", "\n")


def test_cli_help_snapshot_lock():
    targets = {
        "snapshot": "help_snapshot.txt",
        "replay": "help_replay.txt",
        "tune": "help_tune.txt",
        "report": "help_report.txt",
        "strategy": "help_strategy.txt",
        "trace": "help_trace.txt",
        "diff": "help_diff.txt",
    }
    for subcmd, fixture in targets.items():
        assert _run_help(subcmd) == _load_fixture(fixture)
