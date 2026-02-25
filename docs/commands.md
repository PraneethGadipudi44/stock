# CLI Commands

This project exposes a small set of deterministic, file-only commands. No network calls are performed.

See: README.md → “Audit Chain (Deterministic)”.

## Commands

### `audit-manifest`
Derive an audit manifest from existing artifacts (no payload changes).

Required (paths):
- `--as-of YYYY-MM-DD`
- `--brief`, `--brief-meta`
- `--strategy`, `--strategy-meta`
- `--trace`, `--trace-meta`
- `--diff-strategy`, `--diff-strategy-meta`
- `--diff-trace`, `--diff-trace-meta`
- `--out`
- `--meta-out`

Optional:
- `--diff-strategy-md`
- `--diff-trace-md`

### `verify-manifest`
Verify an audit manifest against artifacts (integrity + as_of coherence + hashes).

Required (paths):
- `--manifest`
- `--brief`, `--brief-meta`
- `--strategy`, `--strategy-meta`
- `--trace`, `--trace-meta`
- `--diff-strategy`, `--diff-strategy-meta`
- `--diff-trace`, `--diff-trace-meta`

Optional:
- `--manifest-meta` (defaults to `<manifest>.meta.json` in CLI wiring)
- `--as-of YYYY-MM-DD`
- `--strategy-md`
- `--diff-strategy-md`
- `--diff-trace-md`
- `--out` (writes a hash-only verification report)

### `bundle-manifest`
Bundle manifest + referenced artifacts into a deterministic zip (portable payload).

Required (paths):
- `--manifest`, `--manifest-meta`
- `--brief`, `--brief-meta`
- `--strategy`, `--strategy-meta`
- `--trace`, `--trace-meta`
- `--diff-strategy`, `--diff-strategy-meta`
- `--diff-trace`, `--diff-trace-meta`
- `--out`

Optional:
- `--as-of YYYY-MM-DD`
- `--strategy-md`
- `--diff-strategy-md`
- `--diff-trace-md`

## Exit Codes

| Code | Meaning |
|------|---------|
| 0    | Success |
| 2    | Bad input (missing file / invalid CLI inputs) |
| 3    | Insufficient data / as_of mismatch / coherence failure |
| 4    | Integrity failure (hash mismatch / verification failure) |

## Version

`eds-regime --version` prints the current CLI version string.
