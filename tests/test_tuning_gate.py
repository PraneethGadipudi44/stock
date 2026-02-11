from __future__ import annotations

from core.regime.config import load_regime_config
from core.regime.tuning_harness import run_harness


def test_tuning_conservative_shape_guard():
    rows = run_harness(None)

    assert any(
        row["vote_disagreement_score"] >= 0.6 for row in rows
    ), "Expected at least one high-disagreement scenario"

    cfg = load_regime_config("config/regime_v1.yaml")
    max_conf = float(cfg["confidence"]["bounds"]["max"])

    borderline = [row for row in rows if "borderline" in row["scenario"]]
    assert borderline, "Expected at least one borderline scenario"
    for row in borderline:
        assert row["confidence"] < max_conf