# Design Principles — EDS Regime Engine

1. Determinism first
   - Same inputs + same config must produce identical outputs.
   - No hidden randomness, no time-dependent defaults.

2. Audit trail is mandatory
   - Snapshots are append-only.
   - Config hash + inputs hash are persisted with every snapshot.

3. Config-only tuning
   - Threshold changes belong in YAML, not code.
   - Code changes must be justified and versioned.

4. Conservative defaults
   - Ambiguity resolves to range/neutral/transition.
   - No “force a regime” behavior.

5. Offline-first workflows
   - CSV ingestion works without network.
   - External data providers are optional interfaces.

6. Clear contracts
   - JSON schemas define inputs/outputs.
   - Golden fixtures guard against drift.
