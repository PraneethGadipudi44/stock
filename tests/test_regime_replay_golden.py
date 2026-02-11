from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from core.regime import engine
from core.regime.config import load_regime_config, validate_regime_config
from core.regime.engine import build_regime_snapshot
from core.regime.metrics_builder import build_metrics_from_prices
from core.regime.prices_io import read_prices_csv, rows_to_records


def test_golden_replay_history(monkeypatch):
    uuids = [
        UUID("00000000-0000-0000-0000-0000000000b1"),
        UUID("00000000-0000-0000-0000-0000000000b2"),
        UUID("00000000-0000-0000-0000-0000000000b3"),
        UUID("00000000-0000-0000-0000-0000000000b4"),
        UUID("00000000-0000-0000-0000-0000000000b5"),
    ]
    uuid_iter = iter(uuids)
    monkeypatch.setattr(engine, "uuid4", lambda: next(uuid_iter))

    root = Path(__file__).resolve().parents[1]
    prices_path = root / "tests" / "fixtures" / "prices_small.csv"
    cfg_path = root / "tests" / "fixtures" / "regime_test_cfg.yaml"

    cfg = validate_regime_config(load_regime_config(str(cfg_path)))
    rows = read_prices_csv(str(prices_path))
    dates = sorted({row.date for row in rows})
    dates = dates[-5:]

    previous = None
    history = []

    for current_date in dates:
        subset = [row for row in rows if row.date <= current_date]
        metrics = build_metrics_from_prices(rows_to_records(subset), cfg)
        meta = {
            "as_of_ts": f"{current_date.isoformat()}T00:00:00Z",
            "session": "close",
            "engine_version": "regime_v1",
            "universe": "US_EQ_ETF",
            "benchmarks": ["SPY", "QQQ", "IWM"],
            "reasoning": ["Replay", "Prices fixture", "Deterministic"],
            "metrics_snapshot": {"recent_change_window_days": 20},
        }

        snapshot = build_regime_snapshot(metrics, meta, cfg, previous=previous)
        history.append(
            {
                "date": current_date.isoformat(),
                "snapshot_id": snapshot.snapshot_id,
                "market_phase": snapshot.market_phase,
                "trend_regime": snapshot.trend_regime,
                "vol_regime": snapshot.vol_regime,
                "risk_tone": snapshot.risk_tone,
                "confidence": snapshot.confidence,
                "vote_disagreement_score": snapshot.metrics_snapshot.vote_disagreement_score,
            }
        )
        previous = snapshot

    fixture_path = root / "tests" / "fixtures" / "regime_replay_golden.json"
    expected = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert history == expected
