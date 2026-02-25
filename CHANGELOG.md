# Changelog

## v1.0.0

### Phase 24 — audit-manifest
- Deterministic audit manifest derivation.
- Hash-locked meta + policy tests.

### Phase 25 — bundle-manifest
- Deterministic zip bundle export (portable payload).
- Fixed ordering + fixed timestamps + integrity gate via verify-manifest.

### Phase 26 — verify-manifest
- Strict integrity verification CLI for manifests and artifacts.
- Deterministic, hash-only report option.

### Phase 27 — audit chain docs + smoke test
- README audit chain section documenting end-to-end flow.
- Golden “audit chain” smoke test: manifest → verify → bundle → unzip → verify.
