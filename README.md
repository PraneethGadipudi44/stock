# EDS - Regime Engine

Audit-grade regime engine with deterministic outputs, contract-locked snapshots,
and conservative defaults.

Status: v1.0 Stable (contracts locked, deterministic, invariant-enforced).

## Install
1. Create a virtual environment:
   - Windows: `python -m venv .venv` then `.venv\Scripts\activate`
   - macOS/Linux: `python -m venv .venv` then `source .venv/bin/activate`
2. Install package + dev tools:
   - `pip install -e .`
   - `pip install -r requirements-dev.txt`

## Dev Quickstart
1. Run tests:
   - `python -m pytest -q`
   - Or: `make test`
2. Format, lint, typecheck, build:
   - `make format`
   - `make lint`
   - `make typecheck`
   - `make build`

## CLI
Snapshot from a CSV of daily prices (long format: `date,ticker,close`):

```bash
eds-regime snapshot --cfg config/regime_v1.yaml --prices data/prices_example.csv --out snapshot.json
```

Replay a date range into a local store and emit a summary CSV:

```bash
eds-regime replay --cfg config/regime_v1.yaml --prices data/prices_example.csv --store data/store --start 2025-01-01 --end 2025-12-31 --out replay_summary.csv
```

Run tuning harness scenarios (and optional replay summary):

```bash
eds-regime tune --cfg config/regime_v1.yaml --out tuning.csv
```

Render a human-readable report from a snapshot JSON or the latest store entry:

```bash
eds-regime report --snapshot snapshot.json
eds-regime report --store data/store
```

Store directory can also be provided via:

- `EDS_REGIME_STORE_DIR=/path/to/store`

## Audit Chain (Deterministic)
The audit chain is fully derived and hash-locked. Typical flow:

1. `brief` (brief.json + meta)
2. `strategy-brief`
3. `trace-strategy-brief`
4. `diff-strategy-brief` and `diff-trace-strategy-brief`
5. `audit-manifest`
6. `verify-manifest`
7. `bundle-manifest` (portable bundle)

Minimal commands:

```bash
eds-regime audit-manifest --as-of YYYY-MM-DD --brief ... --brief-meta ... --strategy ... --strategy-meta ... --trace ... --trace-meta ... --diff-strategy ... --diff-strategy-meta ... --diff-trace ... --diff-trace-meta ... --out manifest.json
eds-regime verify-manifest --manifest manifest.json --brief ... --brief-meta ... --strategy ... --strategy-meta ... --trace ... --trace-meta ... --diff-strategy ... --diff-strategy-meta ... --diff-trace ... --diff-trace-meta ...
eds-regime bundle-manifest --manifest manifest.json --manifest-meta manifest.json.meta.json --brief ... --brief-meta ... --strategy ... --strategy-meta ... --trace ... --trace-meta ... --diff-strategy ... --diff-strategy-meta ... --diff-trace ... --diff-trace-meta ... --out audit_bundle.zip
```

## Prices CSV Format
Long format CSV with headers:

```
date,ticker,close
2025-01-01,SPY,100.12
2025-01-01,TLT,89.33
```

Example file:

- `data/prices_example.csv`
- Note: default `regime_v1.yaml` requires ~200 trading days. The example is for format only.

## Snapshot Store
Snapshots are stored as append-only JSONL files under:

- `data/YYYY/MM/regime.jsonl`
- `latest.json` (atomic pointer to the most recent entry)

Each JSONL entry contains:
- `snapshot` (the snapshot JSON)
- `metadata` (stored_at, config_hash, inputs_hash)

## Metrics Definitions
Metrics are computed in `src/core/regime/metrics_builder.py` using the windows
from `config/regime_v1.yaml` under `metrics`.

- `basket_price_above_50dma_pct`: percent of basket tickers with close >= SMA(short)
- `basket_price_above_200dma_pct`: percent of basket tickers with close >= SMA(long)
- `basket_ma50_slope_20d`: percent change of SMA(short) over `slope_window` days
- `chop_score`: CHOP proxy using close-only data
  - `100 * log10(sum(|diff|) / (max(close)-min(close))) / log10(window)`
- `realized_vol_20d_pct`: percentile of annualized realized vol (log returns)
  over `vol_window`, ranked within `vol_lookback`
- `vix_pct`: percentile of latest VIX close within `vix_pct_lookback`
- `hyg_lqd_rs_20d`: (HYG pct change over `rs_window`) - (LQD pct change)
- `spy_tlt_rs_20d`: (SPY pct change over `rs_window`) - (TLT pct change)

## Tuning
Use the tuning harness CSV (`scripts/regime_tuning_harness.py`) and replay
summaries to adjust `config/regime_v1.yaml` thresholds. Keep changes
config-only; engine code stays deterministic and contract-locked.

## API (Optional)
Install with the `api` extra:

```bash
pip install -e .[api]
```

Run:

```bash
uvicorn core.regime.api:create_app --factory --host 0.0.0.0 --port 8000
```

Endpoints:
- `POST /v1/snapshot` (CSV upload or JSON body)
- `GET /v1/latest`
- `GET /v1/snapshots/{id}`
- `GET /v1/history?limit=...`

## Design Principles
See `DESIGN_PRINCIPLES.md`.
