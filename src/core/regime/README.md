# Regime Engine (v1) — Tuning Notes

This module emits a **RegimeSnapshot** used for the Morning Brief and for
strategy gating across the system. The implementation is intentionally
threshold-free until we agree on signal definitions and cutoffs.

## Output Contract
Authoritative JSON schema:
- `contracts/regime_snapshot.schema.json`
Input metrics schema:
- `contracts/regime_metrics_input.schema.v1.json`
Threshold config:
- `config/regime_v1.yaml`

Units note:
- All `*_pct` metrics use a 0–100 scale (percent, not fraction).

Defaults policy:
- `defaults_policy: conservative` means ambiguous votes default to `range` or
  `neutral`, and `market_phase` defaults to `transition` when uncertainty is high.
  Trend classification uses **2-of-3** evidence (position, slope, chop filter)
  under conservative mode.

Key required fields:
- `market_phase`: `trend_up | trend_down | range | transition`
- `trend_regime`: `trend_up | trend_down | range`
- `vol_regime`: `low | normal | high`
- `risk_tone`: `risk_on | neutral | risk_off`
- `signal_votes`: per-signal vote + score + threshold + passed flag
- `metrics_snapshot.vote_disagreement_score`
- `metrics_snapshot.recent_change_window_days`
- `regime_changed`, `change_reason`, `change_drivers`
- `inputs_hash` (optional) for traceability

Note: the Python model uses `datetime` for `as_of_ts`; serialize to ISO-8601
when persisting or emitting JSON.

## Deterministic Transition Criteria
`market_phase=transition` should be derived from explicit metrics, not
heuristic overrides. Use at least:
- `vote_disagreement_score`
- `recent_change_window_days`

## Signal Votes (v1 placeholder)
Each vote should publish a **score**, the **threshold** used, and a
boolean **passed** to make confidence explainable and tunable.

The schema allows additional metrics inside `metrics_snapshot`. The
typed model currently includes only the required fields; we can extend
it when we finalize thresholds.

Trend vote threshold semantics:
- `trend_up` or `trend_down`: `threshold` is always `trend_score_pass`.
- `range` due to CHOP: `threshold` is `chop_high` (passed is True).
- `range` otherwise: `threshold` is `chop_low` (passed is False).

Disagreement safety:
- `metrics_snapshot.vote_disagreement_score` is always computed and clamped to [0,1].
- Extra metrics cannot override required fields; reserved keys are filtered.
- Disagreement weights are config-driven under `thresholds.transition.disagreement_weights`.

Directional trend score (extra):
- `trend_direction_score` is added to `metrics_snapshot.extra` as a signed score:
  positive for `trend_up`, negative for `trend_down`, and `0` for `range`.

## `chop_score` Definition
`chop_score` uses the Choppiness Index (CHOP), scaled 0–100. Compute on
SPY or the benchmark basket using a standard lookback (default 14).

Formula (n = lookback):
- CHOP = 100 * log10( sum(ATR(n)) / (max(high, n) - min(low, n)) ) / log10(n)

Higher values imply range-like conditions; lower values imply trend.

## Regime Change Detection
`compute_regime_changed` should compare the current snapshot to the
prior snapshot and provide:
- `regime_changed: bool`
- `change_reason: str`
- `change_drivers: [enum]`

Suggested drivers (enum):
- `trend_vote_shift`
- `vol_vote_shift`
- `risk_vote_shift`
- `breadth_shift`
- `credit_shift`
- `signal_disagreement`
- `recent_change_window`
- `market_phase_shift`

## Next Tuning Decisions
When we move to implementation, we’ll define:
- Trend position + slope signals (ETF basket)
- Chop/disagreement proxy
- Volatility thresholds (VIX + realized vol percentile)
- Risk-on/off thresholds (credit + equity RS)
- Confidence score aggregation rules
