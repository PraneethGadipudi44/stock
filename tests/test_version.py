from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _env() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    return env


def test_core_version_constant():
    sys.path.insert(0, str(Path.cwd() / "src"))
    import core  # noqa: E402

    assert hasattr(core, "__version__")
    assert core.__version__ == "1.0.0"


def test_cli_version_output_exact():
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "--version",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr
    assert result.stdout == "Regime Engine v1.0.0\n"
    assert result.stderr == ""
