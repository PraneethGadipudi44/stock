from __future__ import annotations

from core.regime.tuning_harness import run_harness


def test_tuning_harness_headers_and_rows():
    rows = run_harness(None)
    assert len(rows) >= 12

    # Intentional: header order is part of the tuning artifact contract.
    # Update this list alongside docs/TUNING.md if columns change.
    expected_headers = [
        "scenario",
        "market_phase",
        "trend_regime",
        "vol_regime",
        "risk_tone",
        "confidence",
        "trend_vote",
        "vol_vote",
        "risk_vote",
        "trend_score",
        "vol_score",
        "risk_score",
        "trend_direction_score",
        "vote_disagreement_score",
        "vote_disagreement_score_internal",
        "vote_disagreement_score_provided",
    ]

    assert list(rows[0].keys()) == expected_headers
    for row in rows[1:]:
        assert list(row.keys()) == expected_headers
