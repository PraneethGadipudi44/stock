# Schema Versioning Policy

## Purpose
`schema_version` is the authoritative contract version for regime snapshots.
It exists to make breaking changes explicit, intentional, and auditable.

## Current Posture (Strict)
Only `schema_version == 1` is accepted unless we ship a translator.
Readers should **fail fast** on any other version.

## Compatibility Rules
Compatible changes (stay within the same schema_version):
- Clarifications in descriptions.
- Tightening validation that does not reject previously valid payloads.

Breaking changes (require schema_version bump):
- Adding/removing required fields.
- Changing field types or semantic meanings.
- Changing constraints that reject previously valid payloads.

## Version Bump Checklist (2-minute rule)
1. Update `contracts/regime_snapshot.schema.json`:
   - Set `schema_version` `const` to the new version.
   - Update required fields / constraints as needed.
2. Sync resource copy:
   - `src/core/regime/resources/regime_snapshot.schema.json` must be byte-identical.
3. Update fixtures:
   - Golden snapshots must include the new `schema_version`.
4. Update tests:
   - Schema version guard tests must reflect the new version.
5. Add a short note in the changelog / report explaining the breaking change.

## Back-Compat Expectations
Unless a translator is introduced, **only** the current schema_version is valid.
Future support for older versions must be explicit and tested.
