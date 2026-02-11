# Tuning Workflow (Phase 7A)

This document defines the **evidence-only** tuning workflow. It does **not** change thresholds. It produces tuning artifacts that we review before any config edits.

## Goals
- Produce a repeatable, deterministic tuning dataset.
- Capture votes, scores, disagreement, and confidence for review.
- Avoid modifying contracts, code behavior, or config values.

## Inputs
- Config: `config/regime_v1.yaml` (do not edit during Phase 7A)
- Synthetic scenarios: `src/core/regime/tuning_harness.py`
- Replay fixture: `tests/fixtures/prices_replay_long.csv` (canonical baseline)

## Outputs
- `data/tuning.csv` — synthetic scenarios with votes, scores, and disagreement
- `data/replay_summary.csv` — replay summary over fixture window

## How to Run

### 1) Harness (synthetic scenarios)
```bash
python scripts/regime_tuning_harness.py --out data/tuning.csv
```

### 2) Replay summary (fixture window)
```bash
eds-regime replay \
  --cfg config/regime_v1.yaml \
  --prices tests/fixtures/prices_replay_long.csv \
  --store data/store \
  --start 2026-01-16 \
  --end 2026-01-20 \
  --out data/replay_summary.csv
```

### 3) Combined (Make target)
```bash
make tune
```

## Column Definitions (Harness Output)
- `scenario`: scenario name
- `market_phase`: phase label from engine
- `trend_regime`: trend label
- `vol_regime`: volatility label
- `risk_tone`: risk label
- `confidence`: overall confidence (bounded by config)
- `trend_vote`, `vol_vote`, `risk_vote`: vote classifications
- `trend_score`, `vol_score`, `risk_score`: numeric signal strengths
- `trend_direction_score`: signed trend score (+up, -down, 0 range)
- `vote_disagreement_score`: effective disagreement (max of provided vs internal)
- `vote_disagreement_score_internal`: internal disagreement
- `vote_disagreement_score_provided`: provided disagreement (if any)

Threshold values are defined in `config/regime_v1.yaml`. Compare scores to those thresholds to interpret actionability.

## What “Good Tuning” Means
- **Stability**: small threshold changes should not flip regimes across many scenarios.
- **Conservatism**: ambiguous cases should remain range/neutral/transition.
- **Consistency**: similar inputs should yield similar votes and confidence.
- **No Overfitting**: do not tune to one fixture or one scenario set.

## Phase 7B Reminder
After this workflow is stable, we can tune thresholds by editing **only** `config/regime_v1.yaml`, with before/after evidence from the tuning CSV and replay summary.