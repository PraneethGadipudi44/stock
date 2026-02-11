from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from core.regime.config import load_regime_config, validate_regime_config


def _env() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    return env


def _load_cfg() -> dict:
    cfg_path = Path("tests/fixtures/regime_test_cfg.yaml")
    return validate_regime_config(load_regime_config(str(cfg_path)))


def _snapshot_from_cli(tmp_path: Path) -> dict:
    tmp_path.mkdir(parents=True, exist_ok=True)
    cfg = Path("tests/fixtures/regime_test_cfg.yaml")
    prices = Path("tests/fixtures/prices_small.csv")
    out_json = tmp_path / "snapshot.json"
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "snapshot",
        "--cfg",
        str(cfg),
        "--prices",
        str(prices),
        "--out",
        str(out_json),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr
    return json.loads(out_json.read_text(encoding="utf-8"))


def _explain_from_cli(tmp_path: Path) -> dict:
    tmp_path.mkdir(parents=True, exist_ok=True)
    cfg = Path("tests/fixtures/regime_test_cfg.yaml")
    prices = Path("tests/fixtures/prices_small.csv")
    out_json = tmp_path / "snapshot.json"
    explain = tmp_path / "explain.json"
    cmd = [
        sys.executable,
        "-m",
        "core.regime.cli",
        "snapshot",
        "--cfg",
        str(cfg),
        "--prices",
        str(prices),
        "--out",
        str(out_json),
        "--explain",
        str(explain),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=_env())
    assert result.returncode == 0, result.stderr
    return json.loads(explain.read_text(encoding="utf-8"))


def _range_snapshot(tmp_path: Path) -> dict:
    fixture_path = Path("tests/fixtures/regime_snapshot_golden.json")
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def _transition_snapshot(tmp_path: Path) -> dict:
    fixture_path = Path("tests/fixtures/regime_snapshot_prices_golden.json")
    return json.loads(fixture_path.read_text(encoding="utf-8"))


class TestHardInvariants:
    def test_confidence_bounds(self, tmp_path: Path):
        cfg = _load_cfg()
        snapshot = _snapshot_from_cli(tmp_path / "bounds")
        bounds = cfg["confidence"]["bounds"]
        assert bounds["min"] <= snapshot["confidence"] <= bounds["max"]

    def test_explain_schema_alignment(self, tmp_path: Path):
        snapshot = _snapshot_from_cli(tmp_path / "snap")
        explain = _explain_from_cli(tmp_path / "explain")
        assert explain["schema_version"] == 1
        assert explain["snapshot_schema_version"] == snapshot["schema_version"] == 1

    def test_signal_votes_structure(self, tmp_path: Path):
        snapshot = _snapshot_from_cli(tmp_path / "votes")
        votes = snapshot["signal_votes"]
        assert set(votes.keys()) == {"trend", "vol", "risk"}
        for key in ("trend", "vol", "risk"):
            assert set(votes[key].keys()) == {
                "vote",
                "score",
                "threshold",
                "passed",
            }

    def test_change_drivers_canonical_form(self, tmp_path: Path):
        snapshot = _snapshot_from_cli(tmp_path / "drivers")
        drivers = snapshot["change_drivers"]
        assert drivers == sorted(drivers)
        assert len(drivers) == len(set(drivers))

    def test_reserved_metrics_snapshot_keys(self, tmp_path: Path):
        snapshot = _snapshot_from_cli(tmp_path / "metrics")
        metrics = snapshot["metrics_snapshot"]
        for key in ("vote_disagreement_score", "recent_change_window_days"):
            assert key in metrics
            assert isinstance(metrics[key], (int, float))

    def test_snapshot_keys_match_schema_required(self):
        snapshot = json.loads(
            Path("tests/fixtures/regime_snapshot_golden.json").read_text(
                encoding="utf-8"
            )
        )
        schema = json.loads(
            Path("contracts/regime_snapshot.schema.json").read_text(encoding="utf-8")
        )
        props = set(schema["properties"].keys())
        required = set(schema["required"])
        assert required.issubset(set(snapshot.keys()))
        assert set(snapshot.keys()).issubset(props)


class TestContextualInvariants:
    def test_disagreement_transition_gate(self, tmp_path: Path):
        cfg = _load_cfg()
        snapshot = _transition_snapshot(tmp_path)
        cutoff = cfg["thresholds"]["transition"]["vote_disagreement_score_cutoff"]
        if snapshot["metrics_snapshot"]["vote_disagreement_score"] >= cutoff:
            assert snapshot["market_phase"] == "transition"

    def test_recent_change_transition_gate(self, tmp_path: Path):
        cfg = _load_cfg()
        snapshot = _transition_snapshot(tmp_path)
        cutoff = cfg["thresholds"]["transition"]["recent_change_window_days_cutoff"]
        if snapshot["metrics_snapshot"]["recent_change_window_days"] <= cutoff:
            assert snapshot["market_phase"] == "transition"

    def test_conservative_policy_enforcement(self, tmp_path: Path):
        cfg = _load_cfg()
        if cfg.get("defaults_policy") != "conservative":
            return
        snapshot = _transition_snapshot(tmp_path)
        votes = snapshot["signal_votes"]
        if votes["trend"]["vote"] != "range" and not votes["trend"]["passed"]:
            assert snapshot["market_phase"] == "transition"

    def test_risk_strength_normalization(self, tmp_path: Path):
        explain = _explain_from_cli(tmp_path / "risk_strength")
        risk_vote = explain["signal_votes"]["risk"]
        if risk_vote["vote"] not in {"risk_on", "risk_off"}:
            return
        strength = explain["confidence_breakdown"]["strengths"]["risk"]
        assert 0.0 <= strength <= 1.0


class TestDeterminismInvariants:
    def test_explain_deterministic_bytes(self, tmp_path: Path):
        a = _explain_from_cli(tmp_path / "a")
        b = _explain_from_cli(tmp_path / "b")
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
