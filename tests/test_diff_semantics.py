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


def test_diff_semantics(tmp_path: Path):
    prev_path = Path("tests/fixtures/regime_snapshot_prices_golden.json")
    curr_path = Path("tests/fixtures/regime_snapshot_golden.json")
    out_path = tmp_path / "diff.json"

    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "diff",
        "--prev",
        str(prev_path),
        "--curr",
        str(curr_path),
        "--out",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr

    payload = json.loads(out_path.read_text(encoding="utf-8"))

    assert payload["market_phase_changed"] is True
    assert payload["trend_regime_changed"] is False
    assert payload["vol_regime_changed"] is True
    assert payload["risk_tone_changed"] is True

    assert payload["confidence_delta"] == 46.3312
    assert payload["change_drivers_added"] == []
    assert payload["change_drivers_removed"] == []
    assert payload["metrics_delta"]["vote_disagreement_score_delta"] == -0.6
    assert payload["metrics_delta"]["recent_change_window_days_delta"] == 0

    summary = payload["diff_summary"]
    assert summary[0] == "market_phase: transition -> trend_up"
    assert summary[1] == "confidence: +46.3312"
    assert summary[2] == "trend_regime: unchanged (trend_up)"
    assert summary[3] == "vol_regime: high -> normal"
    assert summary[4] == "risk_tone: neutral -> risk_on"
