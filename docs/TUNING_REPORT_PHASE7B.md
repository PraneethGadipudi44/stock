# Phase 7B Tuning Report (Evidence Only)

Date: 2026-02-10
Scope: Evidence capture + YAML-only tuning applied; no code/contract/golden changes.

## Decision Log
- We accept confidence clamping to 0.0 under sustained extreme disagreement as a strong "do not act" signal.

## Current Shipped Config (Confidence)
```yaml
confidence:
  penalties:
    transition: 32.0
    disagreement_per_point: 65.0
```

## Inputs
- Config: `config/regime_v1.yaml`
- Harness: `src/core/regime/tuning_harness.py`
- Replay fixture: `tests/fixtures/prices_replay_long.csv` (canonical baseline)
- Replay window: 2026-01-16 -> 2026-01-20

## Harness Overview (data/tuning.csv)
- Total scenarios: 16
- Conservative-shape scenarios (transition/range/neutral): 12

### Scenarios Near Thresholds
(Within ~5–10% of key thresholds; good tuning targets)
- `chop_high_borderline` — trend_score 61.8 (chop_high)
- `chop_low_borderline` — trend_score 38.2 (chop_low)
- `vol_high_borderline_realized_risk_off` — vol_score 80.0 (vol_high), risk_score -1.0 (risk boundary)
- `vol_low_borderline` — vol_score 20.0 (vol_low)
- `mixed_up_vol_high_risk_neutral` — vol_score 80.0 (vol_high)
- `trend_up_vol_high` — vol_score 88.0 (near vol_high), risk_score 1.0 (risk boundary)
- `mixed_down_vol_normal_risk_on` — risk_score 1.0 (risk boundary)

### Conservative-Behavior Checks
- Borderline scenarios remain **transition or range**, not trend-forcing.
- Disagreement spikes in `transition_disagreement` and `mixed_*` scenarios as expected.

### Potential Tuning Targets (Observations Only)
- Pre-change: `mixed_down_vol_normal_risk_on` was 83.5 confidence in transition; tuning adjusted disagreement penalty to bring this down.
- `trend_up_vol_high` stays trend_up with high vol (expected), but confidence remains strong.
  If we want "vol high" to dampen more, adjust penalties in Phase 7B.

## Replay Summary (data/replay_summary.csv)
- Baseline window: 2026-01-16 -> 2026-01-20
- Run using `tests/fixtures/prices_replay_long.csv`
- With disagreement_per_point = 65.0 and sustained disagreement = 0.6, confidence can clamp to 0.0 by design.

## Next Steps (Optional)
Only if further tuning is requested:
- Propose YAML-only threshold changes with evidence.
- For each threshold change, show before/after from tuning.csv and replay summary.
- Keep golden fixtures unchanged unless explicitly approved.