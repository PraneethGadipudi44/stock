from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import traceback
from dataclasses import replace
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .config import load_regime_config, validate_regime_config
from .diff import diff_json
from .catalysts_adapter import (
    CatalystError,
    CatalystNoDataError,
    build_catalysts,
    build_meta as build_catalysts_meta,
    cache_paths as catalysts_cache_paths,
    inputs_hash as catalysts_inputs_hash,
    load_filings,
    load_filings_meta,
    load_prices_dates,
    load_prices_meta,
    sha256_hex as catalysts_sha256_hex,
)
from .brief_adapter import (
    BriefError,
    BriefNoDataError,
    build_brief,
    build_meta as build_brief_meta,
    cache_paths as brief_cache_paths,
    inputs_hash as brief_inputs_hash,
    load_catalysts,
    load_catalysts_meta,
    load_filings_meta as load_brief_filings_meta,
    load_filings_tickers,
    load_prices,
    load_prices_meta as load_brief_prices_meta,
    render_markdown,
    sha256_hex as brief_sha256_hex,
)
from .engine import build_regime_snapshot
from .explain import build_explain_payload, explain_json
from .metrics_builder import MetricsBuildError, build_metrics_from_prices
from .prices_adapter import (
    NoDataError,
    ProviderResponseError,
    build_meta,
    cache_paths,
    fetch_polygon_raw,
    normalize_polygon_raw,
    sha256_hex,
)
from .filings_adapter import (
    NoDataError as FilingsNoDataError,
    build_meta as build_filings_meta,
    cache_paths as filings_cache_paths,
    fetch_raw as fetch_filings_raw,
    load_ticker_map,
    normalize_submissions,
    sha256_hex as filings_sha256_hex,
)
from .earnings_adapter import (
    EarningsError,
    build_earnings,
    build_meta as build_earnings_meta,
    cache_paths as earnings_cache_paths,
    inputs_hash as earnings_inputs_hash,
    load_filings as load_earnings_filings,
    load_filings_meta as load_earnings_filings_meta,
    load_prices_calendar,
    load_prices_meta as load_earnings_prices_meta,
    sha256_hex as earnings_sha256_hex,
)
from .models import RegimeSnapshot
from .prices_io import PriceRow, PricesIOError, read_prices_csv, rows_to_records
from .resources import default_config_path
from .run_snapshot import _snapshot_to_dict
from .store import JsonlSnapshotStore, StoreIntegrityError
from .strategy import (
    load_strategy_config,
    strategy_config_hash,
    strategy_json,
    validate_strategy_config,
)
from .trace import trace_json
from .brief_strategy_adapter import (
    StrategyBriefError,
    StrategyBriefNoDataError,
    build_strategy as build_brief_strategy,
    build_meta as build_brief_strategy_meta,
    cache_paths as brief_strategy_cache_paths,
    inputs_hash as brief_strategy_inputs_hash,
    load_brief as load_strategy_brief,
    load_brief_meta as load_strategy_brief_meta,
    load_catalysts_meta as load_strategy_catalysts_meta,
    load_earnings_meta as load_strategy_earnings_meta,
    render_markdown as render_brief_strategy_markdown,
    sha256_hex as brief_strategy_sha256_hex,
    _load_jsonl as load_strategy_jsonl,
    _require_record_keys as require_strategy_record_keys,
)
from .strategy_brief_trace_adapter import (
    StrategyBriefTraceDataError,
    StrategyBriefTraceMetaError,
    build_trace_meta as build_strategy_brief_trace_meta,
    build_trace as build_strategy_brief_trace,
    cache_paths as strategy_brief_trace_cache_paths,
    inputs_hash as strategy_brief_trace_inputs_hash,
    load_brief_meta as load_trace_brief_meta,
    load_catalysts_meta as load_trace_catalysts_meta,
    load_earnings_meta as load_trace_earnings_meta,
    load_strategy as load_trace_strategy_payload,
    load_strategy_meta as load_trace_strategy_meta,
    sha256_hex as strategy_brief_trace_sha256_hex,
    strategy_coverage,
)

DEBUG = False


class CliError(Exception):
    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class BadInputError(CliError):
    def __init__(self, message: str) -> None:
        super().__init__(message, 2)


class InsufficientDataError(CliError):
    def __init__(self, message: str) -> None:
        super().__init__(message, 3)


class ProviderError(CliError):
    def __init__(self, message: str) -> None:
        super().__init__(message, 4)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Regime Engine CLI")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output (stack traces and config path).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot_parser = subparsers.add_parser("snapshot", help="Build a regime snapshot")
    snapshot_parser.add_argument("--cfg", default="", help="Path to regime config")
    snapshot_parser.add_argument("--prices", required=True, help="Path to prices CSV")
    snapshot_parser.add_argument("--out", default="", help="Optional output JSON path")
    snapshot_parser.add_argument(
        "--explain",
        nargs="?",
        const="-",
        default="",
        help="Write explain JSON to path (or '-' for stdout).",
    )
    snapshot_parser.add_argument("--store", default="", help="Optional store directory")
    snapshot_parser.add_argument(
        "--no-clobber",
        action="store_true",
        help="Fail if output file already exists.",
    )
    snapshot_parser.add_argument(
        "--session",
        default="close",
        choices=["premarket", "open", "midday", "close", "afterhours"],
    )
    snapshot_parser.add_argument(
        "--benchmarks",
        default="SPY,QQQ,IWM",
        help="Comma-separated benchmark list",
    )
    snapshot_parser.add_argument(
        "--reasoning",
        action="append",
        default=[],
        help="Reasoning bullet (repeatable)",
    )
    snapshot_parser.add_argument(
        "--recent-change-window-days",
        type=int,
        default=999,
        help="Recent change window days",
    )
    snapshot_parser.add_argument(
        "--inputs-hash",
        default="",
        help="Optional inputs hash override",
    )

    replay_parser = subparsers.add_parser("replay", help="Replay snapshots over time")
    replay_parser.add_argument("--cfg", default="", help="Path to regime config")
    replay_parser.add_argument("--prices", required=True, help="Path to prices CSV")
    replay_parser.add_argument("--store", default="", help="Store directory")
    replay_parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    replay_parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    replay_parser.add_argument(
        "--out", default="", help="Optional output CSV path"
    )
    replay_parser.add_argument(
        "--explain-dir",
        default="",
        help="Write per-day explain JSON files to DIR.",
    )
    replay_parser.add_argument(
        "--no-clobber",
        action="store_true",
        help="Fail if output file already exists.",
    )
    replay_parser.add_argument(
        "--session",
        default="close",
        choices=["premarket", "open", "midday", "close", "afterhours"],
    )

    tune_parser = subparsers.add_parser("tune", help="Run tuning harness scenarios")
    tune_parser.add_argument("--cfg", default="", help="Path to regime config")
    tune_parser.add_argument(
        "--prices", default="", help="Optional prices CSV for replay summary"
    )
    tune_parser.add_argument(
        "--explain",
        nargs="?",
        const="-",
        default="",
        help="Write tuning explain JSON to path (or '-' for stdout).",
    )
    tune_parser.add_argument(
        "--explain-dir",
        default="",
        help="Write per-scenario explain JSON files to DIR.",
    )
    tune_parser.add_argument(
        "--out", required=True, help="Output CSV path for tuning results"
    )
    tune_parser.add_argument(
        "--no-clobber",
        action="store_true",
        help="Fail if output file already exists.",
    )

    report_parser = subparsers.add_parser("report", help="Render a snapshot summary")
    report_parser.add_argument(
        "--snapshot", default="", help="Path to snapshot JSON file"
    )
    report_parser.add_argument(
        "--store", default="", help="Store directory (uses latest.json)"
    )

    strategy_parser = subparsers.add_parser(
        "strategy", help="Build a strategy recommendation"
    )
    strategy_parser.add_argument(
        "--snapshot",
        default="",
        help="Path to snapshot JSON (or '-' for stdin)",
    )
    strategy_parser.add_argument(
        "--store",
        default="",
        help="Store directory (use with --latest)",
    )
    strategy_parser.add_argument(
        "--latest",
        action="store_true",
        help="Use latest snapshot from store",
    )
    strategy_parser.add_argument(
        "--cfg",
        default="",
        help="Path to strategy config",
    )
    strategy_parser.add_argument(
        "--schema-version",
        type=int,
        choices=[1, 2],
        default=2,
        help="Strategy schema version (default: 2).",
    )
    strategy_parser.add_argument(
        "--out",
        default="",
        help="Output strategy JSON path (or '-' for stdout)",
    )
    strategy_parser.add_argument(
        "--no-clobber",
        action="store_true",
        help="Fail if output file already exists.",
    )

    trace_parser = subparsers.add_parser(
        "trace", help="Link strategy and explain artifacts"
    )
    trace_parser.add_argument(
        "--strategy",
        required=True,
        help="Path to strategy JSON (or '-' for stdin)",
    )
    trace_parser.add_argument(
        "--explain",
        required=True,
        help="Path to explain JSON (or '-' for stdin)",
    )
    trace_parser.add_argument(
        "--out",
        default="",
        help="Output trace JSON path (or '-' for stdout)",
    )
    trace_parser.add_argument(
        "--no-clobber",
        action="store_true",
        help="Fail if output file already exists.",
    )

    trace_brief_parser = subparsers.add_parser(
        "trace-strategy-brief",
        help="Link brief-derived strategy artifacts",
    )
    trace_brief_parser.add_argument(
        "--as-of", required=True, help="As-of date (YYYY-MM-DD)"
    )
    trace_brief_parser.add_argument(
        "--brief", required=True, help="Brief JSON path"
    )
    trace_brief_parser.add_argument(
        "--brief-meta", required=True, help="Brief meta JSON path"
    )
    trace_brief_parser.add_argument(
        "--earnings", required=True, help="Earnings JSONL path"
    )
    trace_brief_parser.add_argument(
        "--earnings-meta", required=True, help="Earnings meta JSON path"
    )
    trace_brief_parser.add_argument(
        "--catalysts", required=True, help="Catalysts JSONL path"
    )
    trace_brief_parser.add_argument(
        "--catalysts-meta", required=True, help="Catalysts meta JSON path"
    )
    trace_brief_parser.add_argument(
        "--strategy", required=True, help="Strategy JSON path"
    )
    trace_brief_parser.add_argument(
        "--strategy-meta", required=True, help="Strategy meta JSON path"
    )
    trace_brief_parser.add_argument(
        "--markdown", default="", help="Optional strategy markdown path"
    )
    trace_brief_parser.add_argument(
        "--out", required=True, help="Output trace JSON path"
    )
    trace_brief_parser.add_argument(
        "--meta-out", default="", help="Optional output trace meta JSON path"
    )
    trace_brief_parser.add_argument(
        "--cache-dir", default=".cache/traces", help="Cache directory"
    )
    trace_brief_parser.add_argument(
        "--cache-only",
        action="store_true",
        help="Fail if cache is missing; do not recompute.",
    )
    trace_brief_parser.add_argument(
        "--refresh",
        action="store_true",
        help="Recompute even if cache exists.",
    )
    trace_brief_parser.add_argument(
        "--no-clobber",
        action="store_true",
        help="Fail if output file already exists.",
    )

    diff_parser = subparsers.add_parser(
        "diff", help="Compare two regime snapshots"
    )
    diff_parser.add_argument("--prev", required=True, help="Path to prev snapshot JSON")
    diff_parser.add_argument("--curr", required=True, help="Path to curr snapshot JSON")
    diff_parser.add_argument(
        "--out",
        default="",
        help="Output diff JSON path (or '-' for stdout)",
    )
    diff_parser.add_argument(
        "--no-clobber",
        action="store_true",
        help="Fail if output file already exists.",
    )

    ingest_parser = subparsers.add_parser(
        "ingest-prices", help="Fetch daily prices and write canonical CSV"
    )
    ingest_parser.add_argument("--symbol", required=True, help="Ticker symbol")
    ingest_parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    ingest_parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    ingest_parser.add_argument("--out", required=True, help="Output CSV path")
    ingest_parser.add_argument(
        "--meta-out",
        default="",
        help="Optional output metadata JSON path",
    )
    ingest_parser.add_argument(
        "--api-key-env",
        default="POLYGON_API_KEY",
        help="Environment variable for Polygon API key",
    )
    ingest_parser.add_argument(
        "--cache-dir",
        default=".cache/prices",
        help="Cache directory for raw provider responses",
    )
    ingest_parser.add_argument(
        "--cache-only",
        action="store_true",
        help="Fail if cache is missing; do not fetch.",
    )
    ingest_parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh cached data from provider.",
    )
    ingest_parser.add_argument(
        "--no-clobber",
        action="store_true",
        help="Fail if output file already exists.",
    )

    filings_parser = subparsers.add_parser(
        "ingest-filings", help="Fetch SEC EDGAR filings and write canonical JSONL"
    )
    filings_parser.add_argument("--ticker", required=True, help="Ticker symbol")
    filings_parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    filings_parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    filings_parser.add_argument("--out", required=True, help="Output JSONL path")
    filings_parser.add_argument(
        "--meta-out",
        default="",
        help="Optional output metadata JSON path",
    )
    filings_parser.add_argument(
        "--cache-dir",
        default=".cache/filings",
        help="Cache directory for SEC responses",
    )
    filings_parser.add_argument(
        "--user-agent",
        required=True,
        help="SEC-compliant User-Agent with contact info",
    )
    filings_parser.add_argument(
        "--cache-only",
        action="store_true",
        help="Fail if cache is missing; do not fetch.",
    )
    filings_parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh cached data from provider.",
    )
    filings_parser.add_argument(
        "--no-clobber",
        action="store_true",
        help="Fail if output file already exists.",
    )

    catalysts_parser = subparsers.add_parser(
        "ingest-catalysts",
        help="Join prices and filings into a catalyst calendar",
    )
    catalysts_parser.add_argument(
        "--prices",
        required=True,
        help="Path to prices CSV",
    )
    catalysts_parser.add_argument(
        "--prices-meta",
        required=True,
        help="Path to prices meta JSON",
    )
    catalysts_parser.add_argument(
        "--filings",
        required=True,
        help="Path to filings JSONL",
    )
    catalysts_parser.add_argument(
        "--filings-meta",
        required=True,
        help="Path to filings meta JSON",
    )
    catalysts_parser.add_argument(
        "--out",
        required=True,
        help="Output catalysts JSONL path",
    )
    catalysts_parser.add_argument(
        "--meta-out",
        default="",
        help="Optional output metadata JSON path",
    )
    catalysts_parser.add_argument(
        "--cache-dir",
        default=".cache/catalysts",
        help="Cache directory for derived catalysts",
    )
    catalysts_parser.add_argument(
        "--cache-only",
        action="store_true",
        help="Fail if cache is missing; do not recompute.",
    )
    catalysts_parser.add_argument(
        "--refresh",
        action="store_true",
        help="Recompute even if cache exists.",
    )
    catalysts_parser.add_argument(
        "--no-clobber",
        action="store_true",
        help="Fail if output file already exists.",
    )

    brief_parser = subparsers.add_parser(
        "brief",
        help="Generate a daily brief from prices, filings, and catalysts",
    )
    brief_parser.add_argument("--as-of", required=True, help="As-of date (YYYY-MM-DD)")
    brief_parser.add_argument("--prices", required=True, help="Prices CSV path")
    brief_parser.add_argument(
        "--prices-meta", required=True, help="Prices meta JSON path"
    )
    brief_parser.add_argument("--filings", required=True, help="Filings JSONL path")
    brief_parser.add_argument(
        "--filings-meta", required=True, help="Filings meta JSON path"
    )
    brief_parser.add_argument(
        "--catalysts", required=True, help="Catalysts JSONL path"
    )
    brief_parser.add_argument(
        "--catalysts-meta", required=True, help="Catalysts meta JSON path"
    )
    brief_parser.add_argument("--out", required=True, help="Output brief JSON path")
    brief_parser.add_argument(
        "--meta-out", default="", help="Optional output brief meta JSON path"
    )
    brief_parser.add_argument(
        "--render-md", default="", help="Optional output brief markdown path"
    )
    brief_parser.add_argument(
        "--cache-dir", default=".cache/briefs", help="Cache directory"
    )
    brief_parser.add_argument(
        "--cache-only",
        action="store_true",
        help="Fail if cache is missing; do not recompute.",
    )
    brief_parser.add_argument(
        "--refresh",
        action="store_true",
        help="Recompute even if cache exists.",
    )
    brief_parser.add_argument(
        "--no-clobber",
        action="store_true",
        help="Fail if output file already exists.",
    )

    brief_strategy_parser = subparsers.add_parser(
        "strategy-brief",
        help="Generate a strategy from a brief and catalyst artifacts",
    )
    brief_strategy_parser.add_argument(
        "--as-of", required=True, help="As-of date (YYYY-MM-DD)"
    )
    brief_strategy_parser.add_argument(
        "--brief", required=True, help="Brief JSON path"
    )
    brief_strategy_parser.add_argument(
        "--brief-meta", required=True, help="Brief meta JSON path"
    )
    brief_strategy_parser.add_argument(
        "--earnings", required=True, help="Earnings JSONL path"
    )
    brief_strategy_parser.add_argument(
        "--earnings-meta", required=True, help="Earnings meta JSON path"
    )
    brief_strategy_parser.add_argument(
        "--catalysts", required=True, help="Catalysts JSONL path"
    )
    brief_strategy_parser.add_argument(
        "--catalysts-meta", required=True, help="Catalysts meta JSON path"
    )
    brief_strategy_parser.add_argument(
        "--out", required=True, help="Output strategy JSON path"
    )
    brief_strategy_parser.add_argument(
        "--meta-out", default="", help="Optional output strategy meta JSON path"
    )
    brief_strategy_parser.add_argument(
        "--render-md", default="", help="Optional output strategy markdown path"
    )
    brief_strategy_parser.add_argument(
        "--cache-dir", default=".cache/strategies", help="Cache directory"
    )
    brief_strategy_parser.add_argument(
        "--cache-only",
        action="store_true",
        help="Fail if cache is missing; do not recompute.",
    )
    brief_strategy_parser.add_argument(
        "--refresh",
        action="store_true",
        help="Recompute even if cache exists.",
    )
    brief_strategy_parser.add_argument(
        "--no-clobber",
        action="store_true",
        help="Fail if output file already exists.",
    )

    earnings_parser = subparsers.add_parser(
        "ingest-earnings",
        help="Derive an earnings calendar from prices and filings",
    )
    earnings_parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    earnings_parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    earnings_parser.add_argument("--prices", required=True, help="Prices CSV path")
    earnings_parser.add_argument(
        "--prices-meta", required=True, help="Prices meta JSON path"
    )
    earnings_parser.add_argument("--filings", required=True, help="Filings JSONL path")
    earnings_parser.add_argument(
        "--filings-meta", required=True, help="Filings meta JSON path"
    )
    earnings_parser.add_argument("--out", required=True, help="Output earnings JSONL path")
    earnings_parser.add_argument(
        "--meta-out", default="", help="Optional output earnings meta JSON path"
    )
    earnings_parser.add_argument(
        "--cache-dir", default=".cache/earnings", help="Cache directory"
    )
    earnings_parser.add_argument(
        "--cache-only",
        action="store_true",
        help="Fail if cache is missing; do not recompute.",
    )
    earnings_parser.add_argument(
        "--refresh",
        action="store_true",
        help="Recompute even if cache exists.",
    )
    earnings_parser.add_argument(
        "--no-clobber",
        action="store_true",
        help="Fail if output file already exists.",
    )

    args = parser.parse_args(argv)
    global DEBUG
    DEBUG = bool(args.debug)

    try:
        if args.command == "snapshot":
            return _run_snapshot(args)
        if args.command == "replay":
            return _run_replay(args)
        if args.command == "tune":
            return _run_tune(args)
        if args.command == "report":
            return _run_report(args)
        if args.command == "strategy":
            return _run_strategy(args)
        if args.command == "trace":
            return _run_trace(args)
        if args.command == "trace-strategy-brief":
            return _run_trace_strategy_brief(args)
        if args.command == "diff":
            return _run_diff(args)
        if args.command == "ingest-prices":
            return _run_ingest_prices(args)
        if args.command == "ingest-filings":
            return _run_ingest_filings(args)
        if args.command == "ingest-catalysts":
            return _run_ingest_catalysts(args)
        if args.command == "brief":
            return _run_brief(args)
        if args.command == "strategy-brief":
            return _run_strategy_brief(args)
        if args.command == "ingest-earnings":
            return _run_ingest_earnings(args)
        return 1
    except CliError as exc:
        _eprint(str(exc))
        if DEBUG:
            traceback.print_exc()
        return exc.exit_code
    except Exception as exc:
        _eprint(f"Unexpected error: {exc}")
        if DEBUG:
            traceback.print_exc()
        return 4


def _run_snapshot(args: argparse.Namespace) -> int:
    cfg = _load_cfg(args.cfg)
    rows = _load_prices_csv(args.prices)

    metrics = _build_metrics_safe(rows, cfg)
    as_of_date = _determine_as_of_date(rows, cfg)
    reasoning = _normalize_reasoning(args.reasoning, "CLI snapshot")

    meta = {
        "as_of_ts": _as_of_ts(as_of_date),
        "session": args.session,
        "engine_version": cfg.get("version", "regime_v1"),
        "universe": "US_EQ_ETF",
        "benchmarks": _parse_benchmarks(args.benchmarks),
        "reasoning": reasoning,
        "metrics_snapshot": {
            "recent_change_window_days": int(args.recent_change_window_days),
        },
    }
    if args.inputs_hash:
        meta["inputs_hash"] = args.inputs_hash

    snapshot_json = _build_snapshot_json(metrics, meta, cfg)
    snapshot_payload = json.loads(snapshot_json)

    if args.out:
        _write_text(Path(args.out), snapshot_json, args.no_clobber)
    else:
        print(snapshot_json)

    if args.explain:
        if args.explain == "-" and not args.out:
            raise BadInputError("Use --out when --explain writes to stdout.")
        resolved_cfg = _resolve_cfg_path(args.cfg)
        cfg_source = resolved_cfg if resolved_cfg else "packaged"
        explain_output = explain_json(
            snapshot_payload, metrics, cfg, cfg_source, resolved_cfg
        )
        if args.explain == "-":
            print(explain_output)
        else:
            _write_text(Path(args.explain), explain_output, args.no_clobber)

    store_dir = _resolve_store_dir(args.store)
    if store_dir:
        store = JsonlSnapshotStore(Path(store_dir), cfg_path=_cfg_path_obj(args.cfg))
        try:
            store.append(snapshot_json, no_clobber=args.no_clobber)
        except StoreIntegrityError as exc:
            raise BadInputError(f"Store error: {exc}") from exc

    return 0


def _run_replay(args: argparse.Namespace) -> int:
    cfg = _load_cfg(args.cfg)
    rows = _load_prices_csv(args.prices)

    start = _parse_date(args.start)
    end = _parse_date(args.end)
    if start > end:
        raise BadInputError("Start date must be <= end date.")

    dates = sorted({row.date for row in rows if start <= row.date <= end})
    if not dates:
        raise InsufficientDataError("No prices within the requested date range.")

    store_dir = _resolve_store_dir(args.store)
    if not store_dir:
        raise BadInputError("Store directory is required for replay.")
    store_path = Path(store_dir)
    store_path.mkdir(parents=True, exist_ok=True)
    store = JsonlSnapshotStore(store_path, cfg_path=_cfg_path_obj(args.cfg))
    summary_rows = []
    explain_dir = Path(args.explain_dir) if args.explain_dir else None
    if explain_dir:
        explain_dir.mkdir(parents=True, exist_ok=True)
        resolved_cfg = _resolve_cfg_path(args.cfg)
        cfg_source = resolved_cfg if resolved_cfg else "packaged"

    previous: Optional[RegimeSnapshot] = None
    days_since_change = 999

    for current_date in dates:
        subset = [row for row in rows if row.date <= current_date]
        metrics = _build_metrics_safe(subset, cfg)
        reasoning = _normalize_reasoning([], f"Replay {current_date.isoformat()}")
        meta = {
            "as_of_ts": _as_of_ts(current_date),
            "session": args.session,
            "engine_version": cfg.get("version", "regime_v1"),
            "universe": "US_EQ_ETF",
            "benchmarks": _parse_benchmarks("SPY,QQQ,IWM"),
            "reasoning": reasoning,
            "metrics_snapshot": {
                "recent_change_window_days": int(days_since_change),
            },
        }

        snapshot = build_regime_snapshot(metrics, meta, cfg, previous=previous)
        snapshot = _apply_deterministic_id(snapshot)
        payload = _snapshot_to_dict(snapshot)
        snapshot_json = json.dumps(payload, sort_keys=True, indent=2)
        try:
            existing = store.get(snapshot.snapshot_id)
            if existing is not None:
                if args.no_clobber:
                    raise BadInputError(
                        f"Snapshot {snapshot.snapshot_id} already exists in store."
                    )
                store._write_latest(existing)
            else:
                store.append(snapshot_json)
        except StoreIntegrityError as exc:
            raise BadInputError(f"Store error: {exc}") from exc

        if explain_dir:
            explain_output = explain_json(
                payload, metrics, cfg, cfg_source, resolved_cfg
            )
            explain_path = explain_dir / (
                f"{current_date.isoformat()}_{snapshot.snapshot_id}.explain.json"
            )
            _write_text(explain_path, explain_output, args.no_clobber)

        summary_rows.append(
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

        if snapshot.regime_changed:
            days_since_change = 0
        else:
            days_since_change += 1
        previous = snapshot

    _write_csv(summary_rows, args.out, args.no_clobber)
    return 0


def _run_tune(args: argparse.Namespace) -> int:
    cfg_path = _resolve_cfg_path(args.cfg)
    harness_rows = _run_harness(cfg_path)

    rows = [
        {"source": "harness", **row}
        for row in harness_rows
    ]

    if args.prices:
        replay_rows = _run_replay_summary(cfg_path, args.prices)
        rows.extend(replay_rows)

    _write_csv(rows, args.out, args.no_clobber)
    if args.explain or args.explain_dir:
        _write_tune_explain(args, cfg_path)
    return 0


def _run_report(args: argparse.Namespace) -> int:
    if args.snapshot:
        snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    else:
        store_dir = _resolve_store_dir(args.store)
        if not store_dir:
            raise BadInputError(
                "Provide --snapshot or set --store / EDS_REGIME_STORE_DIR."
            )
        store = JsonlSnapshotStore(Path(store_dir))
        try:
            latest = store.latest()
        except StoreIntegrityError as exc:
            raise BadInputError(f"Store error: {exc}") from exc
        if latest is None:
            raise BadInputError("No snapshots found in store.")
        snapshot = latest["snapshot"]

    report = _format_report(snapshot)
    print(report)
    return 0


def _run_strategy(args: argparse.Namespace) -> int:
    if args.snapshot and args.latest:
        raise BadInputError("Use either --snapshot or --latest, not both.")

    snapshot: Dict[str, Any]
    if args.snapshot:
        if args.snapshot == "-":
            snapshot = json.loads(sys.stdin.read())
        else:
            snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    else:
        if not args.latest:
            raise BadInputError("Provide --snapshot or --store with --latest.")
        store_dir = _resolve_store_dir(args.store)
        if not store_dir:
            raise BadInputError("Store directory is required for --latest.")
        store = JsonlSnapshotStore(Path(store_dir))
        try:
            latest = store.latest()
        except StoreIntegrityError as exc:
            raise BadInputError(f"Store error: {exc}") from exc
        if latest is None:
            raise BadInputError("No snapshots found in store.")
        snapshot = latest["snapshot"]

    cfg_path = _resolve_cfg_path(args.cfg)
    cfg_source = cfg_path if cfg_path else "packaged"
    cfg = validate_strategy_config(load_strategy_config(cfg_path))
    cfg_hash = strategy_config_hash(cfg_path)
    if args.schema_version == 1:
        _eprint("Warning: --schema-version 1 is legacy; default is v2.")

    output = strategy_json(snapshot, cfg, cfg_source, cfg_hash, args.schema_version)

    if args.out and args.out != "-":
        _write_text(Path(args.out), output, args.no_clobber)
    else:
        print(output)
    return 0


def _run_trace(args: argparse.Namespace) -> int:
    if args.strategy == "-" and args.explain == "-":
        raise BadInputError("Use stdin for only one input at a time.")

    strategy_payload: Dict[str, Any]
    explain_payload: Dict[str, Any]

    if args.strategy == "-":
        strategy_payload = json.loads(sys.stdin.read())
    else:
        strategy_payload = json.loads(
            Path(args.strategy).read_text(encoding="utf-8")
        )

    if args.explain == "-":
        explain_payload = json.loads(sys.stdin.read())
    else:
        explain_payload = json.loads(
            Path(args.explain).read_text(encoding="utf-8")
        )

    try:
        output = trace_json(
            strategy_payload,
            explain_payload,
            strategy_file=args.strategy,
            explain_file=args.explain,
        )
    except ValueError as exc:
        raise BadInputError(str(exc)) from exc

    if args.out and args.out != "-":
        _write_text(Path(args.out), output, args.no_clobber)
    else:
        print(output)

    return 0


def _run_trace_strategy_brief(args: argparse.Namespace) -> int:
    as_of = args.as_of.strip()
    if not as_of:
        raise BadInputError("as_of is required.")
    _parse_date(as_of)

    brief_path = Path(args.brief)
    brief_meta_path = Path(args.brief_meta)
    earnings_path = Path(args.earnings)
    earnings_meta_path = Path(args.earnings_meta)
    catalysts_path = Path(args.catalysts)
    catalysts_meta_path = Path(args.catalysts_meta)
    strategy_path = Path(args.strategy)
    strategy_meta_path = Path(args.strategy_meta)

    for path, label in [
        (brief_path, "brief"),
        (brief_meta_path, "brief meta"),
        (earnings_path, "earnings"),
        (earnings_meta_path, "earnings meta"),
        (catalysts_path, "catalysts"),
        (catalysts_meta_path, "catalysts meta"),
        (strategy_path, "strategy"),
        (strategy_meta_path, "strategy meta"),
    ]:
        if not path.exists():
            raise BadInputError(f"{label} file not found: {path}")

    try:
        brief_meta = load_trace_brief_meta(brief_meta_path)
        earnings_meta = load_trace_earnings_meta(earnings_meta_path)
        catalysts_meta = load_trace_catalysts_meta(catalysts_meta_path)
        strategy_meta = load_trace_strategy_meta(strategy_meta_path)
    except StrategyBriefTraceMetaError as exc:
        raise BadInputError(str(exc)) from exc

    brief_bytes = brief_path.read_bytes()
    earnings_bytes = earnings_path.read_bytes()
    catalysts_bytes = catalysts_path.read_bytes()
    strategy_bytes = strategy_path.read_bytes()

    brief_hash = strategy_brief_trace_sha256_hex(brief_bytes)
    if brief_meta.get("normalized_brief_hash") != brief_hash:
        raise ProviderError("Cache corruption detected (brief hash mismatch).")

    earnings_hash = strategy_brief_trace_sha256_hex(earnings_bytes)
    if earnings_meta.get("normalized_jsonl_hash") != earnings_hash:
        raise ProviderError("Cache corruption detected (earnings hash mismatch).")

    catalysts_hash = strategy_brief_trace_sha256_hex(catalysts_bytes)
    if catalysts_meta.get("normalized_jsonl_hash") != catalysts_hash:
        raise ProviderError("Cache corruption detected (catalysts hash mismatch).")

    strategy_hash = strategy_brief_trace_sha256_hex(strategy_bytes)
    if strategy_meta.get("normalized_strategy_hash") != strategy_hash:
        raise ProviderError("Cache corruption detected (strategy hash mismatch).")

    markdown_hash: Optional[str] = None
    if args.markdown:
        md_path = Path(args.markdown)
        if not md_path.exists():
            raise BadInputError(f"markdown file not found: {md_path}")
        markdown_hash = strategy_brief_trace_sha256_hex(md_path.read_bytes())

    inputs_digest = strategy_brief_trace_inputs_hash(
        as_of, brief_hash, earnings_hash, catalysts_hash, strategy_hash, markdown_hash
    )

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths = strategy_brief_trace_cache_paths(cache_dir, inputs_digest)
    paths.trace.parent.mkdir(parents=True, exist_ok=True)

    cache_hit = paths.trace.exists() and paths.meta.exists()
    if args.cache_only and not cache_hit:
        raise ProviderError("Cache miss and --cache-only set.")

    if cache_hit and not args.refresh:
        cached_trace = paths.trace.read_bytes()
        cached_meta = json.loads(paths.meta.read_text(encoding="utf-8"))
        cached_hash = strategy_brief_trace_sha256_hex(cached_trace)
        if cached_meta.get("normalized_trace_hash") != cached_hash:
            raise ProviderError("Cache corruption detected (trace hash mismatch).")
        trace_bytes = cached_trace
        meta_text = json.dumps(cached_meta, indent=2, sort_keys=True)
    else:
        try:
            strategy_payload = load_trace_strategy_payload(strategy_path)
        except StrategyBriefTraceDataError as exc:
            raise ProviderError(str(exc)) from exc

        if strategy_payload.get("as_of") != as_of:
            raise InsufficientDataError(
                "Strategy as_of does not match requested as_of."
            )

        coverage = strategy_coverage(strategy_payload)
        trace_payload = build_strategy_brief_trace(
            as_of=as_of,
            brief_hash=brief_hash,
            earnings_hash=earnings_hash,
            catalysts_hash=catalysts_hash,
            strategy_hash=strategy_hash,
            markdown_hash=markdown_hash,
            coverage=coverage,
        )
        trace_text = json.dumps(trace_payload, indent=2, sort_keys=True)
        trace_bytes = trace_text.encode("utf-8")
        trace_hash = strategy_brief_trace_sha256_hex(trace_bytes)

        meta = build_strategy_brief_trace_meta(
            brief_hash=brief_hash,
            earnings_hash=earnings_hash,
            catalysts_hash=catalysts_hash,
            strategy_hash=strategy_hash,
            markdown_hash=markdown_hash,
            inputs_digest=inputs_digest,
            trace_hash=trace_hash,
            coverage=coverage,
            cache_hit=bool(cache_hit),
        )
        meta_text = json.dumps(meta, indent=2, sort_keys=True)

        paths.trace.write_bytes(trace_bytes)
        paths.meta.write_text(meta_text, encoding="utf-8")

    out_path = Path(args.out)
    meta_out = Path(args.meta_out) if args.meta_out else out_path.with_suffix(
        out_path.suffix + ".meta.json"
    )
    _check_no_clobber(out_path, args.no_clobber)
    _check_no_clobber(meta_out, args.no_clobber)

    out_path.write_bytes(trace_bytes)
    meta_out.write_text(meta_text, encoding="utf-8")

    return 0


def _run_diff(args: argparse.Namespace) -> int:
    prev = json.loads(Path(args.prev).read_text(encoding="utf-8"))
    curr = json.loads(Path(args.curr).read_text(encoding="utf-8"))
    try:
        output = diff_json(prev, curr)
    except ValueError as exc:
        raise BadInputError(str(exc)) from exc

    if args.out and args.out != "-":
        _write_text(Path(args.out), output, args.no_clobber)
    else:
        print(output)
    return 0


def _run_ingest_prices(args: argparse.Namespace) -> int:
    symbol = args.symbol.strip().upper()
    if not symbol:
        raise BadInputError("Symbol cannot be empty.")

    start = _parse_date(args.start).isoformat()
    end = _parse_date(args.end).isoformat()
    if start > end:
        raise BadInputError("Start date must be <= end date.")

    cache_dir = Path(args.cache_dir)
    paths = cache_paths(cache_dir, symbol, start, end)
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths.raw.parent.mkdir(parents=True, exist_ok=True)

    cache_hit = paths.raw.exists()
    raw_bytes: Optional[bytes] = None

    if args.cache_only:
        if not cache_hit:
            raise ProviderError("Cache miss and --cache-only set.")
        raw_bytes = paths.raw.read_bytes()
        cache_hit = True
    else:
        if cache_hit and not args.refresh:
            raw_bytes = paths.raw.read_bytes()
        else:
            api_key = os.environ.get(args.api_key_env, "")
            if not api_key:
                raise BadInputError(
                    f"Missing API key in environment variable {args.api_key_env}."
                )
            try:
                raw_bytes = fetch_polygon_raw(symbol, start, end, api_key)
            except ProviderResponseError as exc:
                raise ProviderError(str(exc)) from exc
            paths.raw.write_bytes(raw_bytes)
            cache_hit = False

    if paths.meta.exists():
        try:
            cached_meta = json.loads(paths.meta.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProviderError("Cache corruption detected (meta JSON invalid).") from exc
        raw_hash_check = sha256_hex(raw_bytes)
        if cached_meta.get("source_hash") != raw_hash_check:
            raise ProviderError("Cache corruption detected (raw hash mismatch).")

    try:
        csv_text, rows = normalize_polygon_raw(raw_bytes, symbol)
    except NoDataError as exc:
        raise InsufficientDataError(str(exc)) from exc
    except ProviderResponseError as exc:
        raise ProviderError(str(exc)) from exc

    csv_bytes = csv_text.encode("utf-8")
    csv_hash = sha256_hex(csv_bytes)
    raw_hash = sha256_hex(raw_bytes)

    if paths.meta.exists():
        try:
            cached_meta = json.loads(paths.meta.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProviderError("Cache corruption detected (meta JSON invalid).") from exc
        if cached_meta.get("normalized_csv_hash") != csv_hash:
            raise ProviderError("Cache corruption detected (csv hash mismatch).")

    meta = build_meta(
        symbol=symbol,
        start=start,
        end=end,
        request_canonical=paths.request_canonical,
        cache_key=paths.cache_key,
        endpoint=paths.endpoint,
        raw_hash=raw_hash,
        csv_hash=csv_hash,
        rows=rows,
        cache_hit=cache_hit,
    )
    meta_text = json.dumps(meta, indent=2, sort_keys=True)

    out_path = Path(args.out)
    meta_out = Path(args.meta_out) if args.meta_out else out_path.with_suffix(
        out_path.suffix + ".meta.json"
    )

    _check_no_clobber(out_path, args.no_clobber)
    _check_no_clobber(meta_out, args.no_clobber)

    out_path.write_bytes(csv_bytes)
    meta_out.write_text(meta_text, encoding="utf-8")

    paths.csv.write_bytes(csv_bytes)
    paths.meta.write_text(meta_text, encoding="utf-8")

    return 0


def _run_ingest_filings(args: argparse.Namespace) -> int:
    ticker = args.ticker.strip().upper()
    if not ticker:
        raise BadInputError("Ticker cannot be empty.")
    if not args.user_agent.strip():
        raise BadInputError("User-Agent is required.")

    start = _parse_date(args.start).isoformat()
    end = _parse_date(args.end).isoformat()
    if start > end:
        raise BadInputError("Start date must be <= end date.")

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    try:
        ticker_map, _ = load_ticker_map(
            cache_dir,
            args.user_agent,
            cache_only=bool(args.cache_only),
            refresh=bool(args.refresh),
        )
    except ProviderResponseError as exc:
        raise ProviderError(str(exc)) from exc

    if ticker not in ticker_map:
        raise BadInputError(f"Unknown ticker: {ticker}")
    cik_padded = ticker_map[ticker]

    paths = filings_cache_paths(cache_dir, ticker, start, end, cik_padded)
    paths.raw.parent.mkdir(parents=True, exist_ok=True)

    cache_hit = paths.raw.exists()
    raw_bytes: Optional[bytes] = None

    if args.cache_only:
        if not cache_hit:
            raise ProviderError("Cache miss and --cache-only set.")
        raw_bytes = paths.raw.read_bytes()
        cache_hit = True
    else:
        if cache_hit and not args.refresh:
            raw_bytes = paths.raw.read_bytes()
        else:
            url = f"https://data.sec.gov{paths.endpoint}"
            try:
                raw_bytes = fetch_filings_raw(url, args.user_agent)
            except ProviderResponseError as exc:
                raise ProviderError(str(exc)) from exc
            paths.raw.write_bytes(raw_bytes)
            cache_hit = False

    if paths.meta.exists():
        try:
            cached_meta = json.loads(paths.meta.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProviderError("Cache corruption detected (meta JSON invalid).") from exc
        raw_hash_check = filings_sha256_hex(raw_bytes)
        if cached_meta.get("source_hash") != raw_hash_check:
            raise ProviderError("Cache corruption detected (raw hash mismatch).")

    try:
        jsonl_text, rows = normalize_submissions(
            raw_bytes,
            ticker=ticker,
            cik_padded=cik_padded,
            start=start,
            end=end,
        )
    except FilingsNoDataError as exc:
        raise InsufficientDataError(str(exc)) from exc
    except ProviderResponseError as exc:
        raise ProviderError(str(exc)) from exc

    jsonl_bytes = jsonl_text.encode("utf-8")
    jsonl_hash = filings_sha256_hex(jsonl_bytes)
    raw_hash = filings_sha256_hex(raw_bytes)

    if paths.meta.exists():
        try:
            cached_meta = json.loads(paths.meta.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProviderError("Cache corruption detected (meta JSON invalid).") from exc
        if cached_meta.get("normalized_jsonl_hash") != jsonl_hash:
            raise ProviderError("Cache corruption detected (jsonl hash mismatch).")

    meta = build_filings_meta(
        ticker=ticker,
        cik=cik_padded,
        start=start,
        end=end,
        request_canonical=paths.request_canonical,
        cache_key=paths.cache_key,
        raw_hash=raw_hash,
        jsonl_hash=jsonl_hash,
        rows=rows,
        cache_hit=cache_hit,
    )
    meta_text = json.dumps(meta, indent=2, sort_keys=True)

    out_path = Path(args.out)
    meta_out = Path(args.meta_out) if args.meta_out else out_path.with_suffix(
        out_path.suffix + ".meta.json"
    )

    _check_no_clobber(out_path, args.no_clobber)
    _check_no_clobber(meta_out, args.no_clobber)

    out_path.write_bytes(jsonl_bytes)
    meta_out.write_text(meta_text, encoding="utf-8")

    paths.jsonl.write_bytes(jsonl_bytes)
    paths.meta.write_text(meta_text, encoding="utf-8")

    return 0


def _run_ingest_catalysts(args: argparse.Namespace) -> int:
    prices_path = Path(args.prices)
    prices_meta_path = Path(args.prices_meta)
    filings_path = Path(args.filings)
    filings_meta_path = Path(args.filings_meta)

    if not prices_path.exists():
        raise BadInputError(f"Prices file not found: {prices_path}")
    if not prices_meta_path.exists():
        raise BadInputError(f"Prices meta file not found: {prices_meta_path}")
    if not filings_path.exists():
        raise BadInputError(f"Filings file not found: {filings_path}")
    if not filings_meta_path.exists():
        raise BadInputError(f"Filings meta file not found: {filings_meta_path}")

    try:
        prices_meta = load_prices_meta(prices_meta_path)
        filings_meta = load_filings_meta(filings_meta_path)
    except CatalystError as exc:
        raise BadInputError(str(exc)) from exc

    prices_bytes = prices_path.read_bytes()
    filings_bytes = filings_path.read_bytes()

    prices_hash = catalysts_sha256_hex(prices_bytes)
    if prices_meta.get("normalized_csv_hash") != prices_hash:
        raise ProviderError("Cache corruption detected (prices hash mismatch).")

    filings_hash = catalysts_sha256_hex(filings_bytes)
    if filings_meta.get("normalized_jsonl_hash") != filings_hash:
        raise ProviderError("Cache corruption detected (filings hash mismatch).")

    inputs_digest = catalysts_inputs_hash(prices_hash, filings_hash)

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths = catalysts_cache_paths(cache_dir, inputs_digest)
    paths.jsonl.parent.mkdir(parents=True, exist_ok=True)

    cache_hit = paths.jsonl.exists() and paths.meta.exists()
    if args.cache_only and not cache_hit:
        raise ProviderError("Cache miss and --cache-only set.")

    if cache_hit and not args.refresh:
        cached_jsonl = paths.jsonl.read_bytes()
        cached_meta = json.loads(paths.meta.read_text(encoding="utf-8"))
        cached_hash = catalysts_sha256_hex(cached_jsonl)
        if cached_meta.get("normalized_jsonl_hash") != cached_hash:
            raise ProviderError("Cache corruption detected (catalysts hash mismatch).")
        jsonl_bytes = cached_jsonl
        meta_text = json.dumps(cached_meta, indent=2, sort_keys=True)
        rows = int(cached_meta.get("rows", 0))
    else:
        try:
            price_dates = load_prices_dates(prices_path)
            filings_records = load_filings(filings_path)
            jsonl_text, rows = build_catalysts(filings_records, price_dates)
        except CatalystNoDataError as exc:
            raise InsufficientDataError(str(exc)) from exc
        except CatalystError as exc:
            raise ProviderError(str(exc)) from exc

        jsonl_bytes = jsonl_text.encode("utf-8")
        jsonl_hash = catalysts_sha256_hex(jsonl_bytes)
        meta = build_catalysts_meta(
            prices_meta=prices_meta,
            filings_meta=filings_meta,
            inputs_digest=inputs_digest,
            jsonl_hash=jsonl_hash,
            rows=rows,
            cache_hit=bool(cache_hit),
        )
        meta_text = json.dumps(meta, indent=2, sort_keys=True)

        paths.jsonl.write_bytes(jsonl_bytes)
        paths.meta.write_text(meta_text, encoding="utf-8")

    out_path = Path(args.out)
    meta_out = Path(args.meta_out) if args.meta_out else out_path.with_suffix(
        out_path.suffix + ".meta.json"
    )

    _check_no_clobber(out_path, args.no_clobber)
    _check_no_clobber(meta_out, args.no_clobber)

    out_path.write_bytes(jsonl_bytes)
    meta_out.write_text(meta_text, encoding="utf-8")

    if rows == 0:
        raise InsufficientDataError("No catalysts in requested join.")

    return 0


def _run_ingest_earnings(args: argparse.Namespace) -> int:
    start = _parse_date(args.start).isoformat()
    end = _parse_date(args.end).isoformat()
    if start > end:
        raise BadInputError("Start date must be <= end date.")

    prices_path = Path(args.prices)
    prices_meta_path = Path(args.prices_meta)
    filings_path = Path(args.filings)
    filings_meta_path = Path(args.filings_meta)

    for path, label in [
        (prices_path, "prices"),
        (prices_meta_path, "prices meta"),
        (filings_path, "filings"),
        (filings_meta_path, "filings meta"),
    ]:
        if not path.exists():
            raise BadInputError(f"{label} file not found: {path}")

    try:
        prices_meta = load_earnings_prices_meta(prices_meta_path)
        filings_meta = load_earnings_filings_meta(filings_meta_path)
    except EarningsError as exc:
        raise BadInputError(str(exc)) from exc

    prices_bytes = prices_path.read_bytes()
    filings_bytes = filings_path.read_bytes()

    prices_hash = earnings_sha256_hex(prices_bytes)
    if prices_meta.get("normalized_csv_hash") != prices_hash:
        raise ProviderError("Cache corruption detected (prices hash mismatch).")

    filings_hash = earnings_sha256_hex(filings_bytes)
    if filings_meta.get("normalized_jsonl_hash") != filings_hash:
        raise ProviderError("Cache corruption detected (filings hash mismatch).")

    inputs_digest = earnings_inputs_hash(start, end, prices_hash, filings_hash)

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths = earnings_cache_paths(cache_dir, inputs_digest)
    paths.jsonl.parent.mkdir(parents=True, exist_ok=True)

    cache_hit = paths.jsonl.exists() and paths.meta.exists()
    if args.cache_only and not cache_hit:
        raise ProviderError("Cache miss and --cache-only set.")

    if cache_hit and not args.refresh:
        cached_jsonl = paths.jsonl.read_bytes()
        cached_meta = json.loads(paths.meta.read_text(encoding="utf-8"))
        cached_hash = earnings_sha256_hex(cached_jsonl)
        if cached_meta.get("normalized_jsonl_hash") != cached_hash:
            raise ProviderError("Cache corruption detected (earnings hash mismatch).")
        jsonl_bytes = cached_jsonl
        meta_text = json.dumps(cached_meta, indent=2, sort_keys=True)
    else:
        try:
            price_dates = load_prices_calendar(prices_path)
            filings_records = load_earnings_filings(filings_path)
            jsonl_text, rows = build_earnings(
                filings_records, price_dates, start, end
            )
        except EarningsError as exc:
            raise ProviderError(str(exc)) from exc

        jsonl_bytes = jsonl_text.encode("utf-8")
        jsonl_hash = earnings_sha256_hex(jsonl_bytes)
        meta = build_earnings_meta(
            prices_meta=prices_meta,
            filings_meta=filings_meta,
            inputs_digest=inputs_digest,
            jsonl_hash=jsonl_hash,
            rows=rows,
            cache_hit=bool(cache_hit),
        )
        meta_text = json.dumps(meta, indent=2, sort_keys=True)

        paths.jsonl.write_bytes(jsonl_bytes)
        paths.meta.write_text(meta_text, encoding="utf-8")

    out_path = Path(args.out)
    meta_out = Path(args.meta_out) if args.meta_out else out_path.with_suffix(
        out_path.suffix + ".meta.json"
    )

    _check_no_clobber(out_path, args.no_clobber)
    _check_no_clobber(meta_out, args.no_clobber)

    out_path.write_bytes(jsonl_bytes)
    meta_out.write_text(meta_text, encoding="utf-8")

    return 0


def _run_brief(args: argparse.Namespace) -> int:
    as_of = args.as_of.strip()
    if not as_of:
        raise BadInputError("as_of is required.")

    prices_path = Path(args.prices)
    prices_meta_path = Path(args.prices_meta)
    filings_path = Path(args.filings)
    filings_meta_path = Path(args.filings_meta)
    catalysts_path = Path(args.catalysts)
    catalysts_meta_path = Path(args.catalysts_meta)

    for path, label in [
        (prices_path, "prices"),
        (prices_meta_path, "prices meta"),
        (filings_path, "filings"),
        (filings_meta_path, "filings meta"),
        (catalysts_path, "catalysts"),
        (catalysts_meta_path, "catalysts meta"),
    ]:
        if not path.exists():
            raise BadInputError(f"{label} file not found: {path}")

    try:
        prices_meta = load_brief_prices_meta(prices_meta_path)
        filings_meta = load_brief_filings_meta(filings_meta_path)
        catalysts_meta = load_catalysts_meta(catalysts_meta_path)
    except BriefError as exc:
        raise BadInputError(str(exc)) from exc

    prices_bytes = prices_path.read_bytes()
    filings_bytes = filings_path.read_bytes()
    catalysts_bytes = catalysts_path.read_bytes()

    prices_hash = brief_sha256_hex(prices_bytes)
    if prices_meta.get("normalized_csv_hash") != prices_hash:
        raise ProviderError("Cache corruption detected (prices hash mismatch).")

    filings_hash = brief_sha256_hex(filings_bytes)
    if filings_meta.get("normalized_jsonl_hash") != filings_hash:
        raise ProviderError("Cache corruption detected (filings hash mismatch).")

    catalysts_hash = brief_sha256_hex(catalysts_bytes)
    if catalysts_meta.get("normalized_jsonl_hash") != catalysts_hash:
        raise ProviderError("Cache corruption detected (catalysts hash mismatch).")

    inputs_digest = brief_inputs_hash(as_of, prices_hash, filings_hash, catalysts_hash)

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths = brief_cache_paths(cache_dir, inputs_digest)
    paths.brief.parent.mkdir(parents=True, exist_ok=True)

    cache_hit = paths.brief.exists() and paths.meta.exists()
    if args.cache_only and not cache_hit:
        raise ProviderError("Cache miss and --cache-only set.")

    render_md = bool(args.render_md)
    markdown_text: Optional[str] = None

    if cache_hit and not args.refresh:
        cached_brief = paths.brief.read_bytes()
        cached_meta = json.loads(paths.meta.read_text(encoding="utf-8"))
        cached_hash = brief_sha256_hex(cached_brief)
        if cached_meta.get("normalized_brief_hash") != cached_hash:
            raise ProviderError("Cache corruption detected (brief hash mismatch).")
        brief_bytes = cached_brief
        meta_text = json.dumps(cached_meta, indent=2, sort_keys=True)
        if render_md:
            cached_md = paths.markdown.read_bytes()
            md_hash = brief_sha256_hex(cached_md)
            if cached_meta.get("markdown_hash") != md_hash:
                raise ProviderError("Cache corruption detected (markdown hash mismatch).")
            markdown_text = cached_md.decode("utf-8")
    else:
        try:
            prices, dates, global_dates, prices_rows = load_prices(prices_path)
            filings_rows, filings_tickers = load_filings_tickers(filings_path)
            catalysts = load_catalysts(catalysts_path)
            brief, rows_meta = build_brief(
                as_of=as_of,
                prices=prices,
                dates=dates,
                global_dates=global_dates,
                catalysts=catalysts,
                filings_rows=filings_rows,
                filings_tickers=filings_tickers,
                prices_rows=prices_rows,
            )
        except BriefNoDataError as exc:
            raise InsufficientDataError(str(exc)) from exc
        except BriefError as exc:
            raise ProviderError(str(exc)) from exc

        brief_text = json.dumps(brief, indent=2, sort_keys=True)
        brief_bytes = brief_text.encode("utf-8")
        brief_hash = brief_sha256_hex(brief_bytes)

        markdown_hash: Optional[str] = None
        if render_md:
            markdown_text = render_markdown(brief)
            markdown_hash = brief_sha256_hex(markdown_text.encode("utf-8"))

        meta = build_brief_meta(
            prices_meta=prices_meta,
            filings_meta=filings_meta,
            catalysts_meta=catalysts_meta,
            inputs_digest=inputs_digest,
            brief_hash=brief_hash,
            markdown_hash=markdown_hash,
            rows=rows_meta,
            cache_hit=bool(cache_hit),
        )
        meta_text = json.dumps(meta, indent=2, sort_keys=True)

        paths.brief.write_bytes(brief_bytes)
        paths.meta.write_text(meta_text, encoding="utf-8")
        if render_md and markdown_text is not None:
            paths.markdown.write_text(markdown_text, encoding="utf-8")

    out_path = Path(args.out)
    meta_out = Path(args.meta_out) if args.meta_out else out_path.with_suffix(
        out_path.suffix + ".meta.json"
    )
    _check_no_clobber(out_path, args.no_clobber)
    _check_no_clobber(meta_out, args.no_clobber)

    out_path.write_bytes(brief_bytes)
    meta_out.write_text(meta_text, encoding="utf-8")

    if render_md and markdown_text is not None:
        md_path = Path(args.render_md)
        _check_no_clobber(md_path, args.no_clobber)
        md_path.write_text(markdown_text, encoding="utf-8")

    return 0


def _run_strategy_brief(args: argparse.Namespace) -> int:
    as_of = args.as_of.strip()
    if not as_of:
        raise BadInputError("as_of is required.")

    brief_path = Path(args.brief)
    brief_meta_path = Path(args.brief_meta)
    earnings_path = Path(args.earnings)
    earnings_meta_path = Path(args.earnings_meta)
    catalysts_path = Path(args.catalysts)
    catalysts_meta_path = Path(args.catalysts_meta)

    for path, label in [
        (brief_path, "brief"),
        (brief_meta_path, "brief meta"),
        (earnings_path, "earnings"),
        (earnings_meta_path, "earnings meta"),
        (catalysts_path, "catalysts"),
        (catalysts_meta_path, "catalysts meta"),
    ]:
        if not path.exists():
            raise BadInputError(f"{label} file not found: {path}")

    try:
        brief_meta = load_strategy_brief_meta(brief_meta_path)
        earnings_meta = load_strategy_earnings_meta(earnings_meta_path)
        catalysts_meta = load_strategy_catalysts_meta(catalysts_meta_path)
    except StrategyBriefError as exc:
        raise BadInputError(str(exc)) from exc

    brief_bytes = brief_path.read_bytes()
    earnings_bytes = earnings_path.read_bytes()
    catalysts_bytes = catalysts_path.read_bytes()

    brief_hash = brief_strategy_sha256_hex(brief_bytes)
    if brief_meta.get("normalized_brief_hash") != brief_hash:
        raise ProviderError("Cache corruption detected (brief hash mismatch).")

    earnings_hash = brief_strategy_sha256_hex(earnings_bytes)
    if earnings_meta.get("normalized_jsonl_hash") != earnings_hash:
        raise ProviderError("Cache corruption detected (earnings hash mismatch).")

    catalysts_hash = brief_strategy_sha256_hex(catalysts_bytes)
    if catalysts_meta.get("normalized_jsonl_hash") != catalysts_hash:
        raise ProviderError("Cache corruption detected (catalysts hash mismatch).")

    inputs_digest = brief_strategy_inputs_hash(
        as_of, brief_hash, earnings_hash, catalysts_hash
    )

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths = brief_strategy_cache_paths(cache_dir, inputs_digest)
    paths.strategy.parent.mkdir(parents=True, exist_ok=True)

    cache_hit = paths.strategy.exists() and paths.meta.exists()
    if args.cache_only and not cache_hit:
        raise ProviderError("Cache miss and --cache-only set.")

    render_md = bool(args.render_md)
    markdown_text: Optional[str] = None

    if cache_hit and not args.refresh:
        cached_strategy = paths.strategy.read_bytes()
        cached_meta = json.loads(paths.meta.read_text(encoding="utf-8"))
        cached_hash = brief_strategy_sha256_hex(cached_strategy)
        if cached_meta.get("normalized_strategy_hash") != cached_hash:
            raise ProviderError("Cache corruption detected (strategy hash mismatch).")
        strategy_bytes = cached_strategy
        meta_text = json.dumps(cached_meta, indent=2, sort_keys=True)
        if render_md:
            cached_md = paths.markdown.read_bytes()
            md_hash = brief_strategy_sha256_hex(cached_md)
            if cached_meta.get("markdown_hash") != md_hash:
                raise ProviderError("Cache corruption detected (markdown hash mismatch).")
            markdown_text = cached_md.decode("utf-8")
    else:
        try:
            brief = load_strategy_brief(brief_path)
            earnings_records = load_strategy_jsonl(earnings_path, "Earnings")
            catalysts_records = load_strategy_jsonl(catalysts_path, "Catalysts")
            require_strategy_record_keys(
                earnings_records,
                [
                    "ticker",
                    "event_date",
                    "event_type",
                    "form",
                    "filing_date",
                    "acceptance_datetime",
                    "accession_number",
                    "url_filing_detail",
                ],
                "earnings_record",
            )
            require_strategy_record_keys(
                catalysts_records,
                [
                    "ticker",
                    "event_date",
                    "event_type",
                    "form",
                    "filing_date",
                    "acceptance_datetime",
                    "accession_number",
                    "url_filing_detail",
                    "has_price_row",
                ],
                "catalyst_record",
            )
            strategy, rows_meta = build_brief_strategy(
                as_of=as_of,
                brief=brief,
                earnings_records=earnings_records,
                catalysts_records=catalysts_records,
            )
        except StrategyBriefNoDataError as exc:
            raise InsufficientDataError(str(exc)) from exc
        except StrategyBriefError as exc:
            raise ProviderError(str(exc)) from exc

        strategy_text = json.dumps(strategy, indent=2, sort_keys=True)
        strategy_bytes = strategy_text.encode("utf-8")
        strategy_hash = brief_strategy_sha256_hex(strategy_bytes)

        markdown_hash: Optional[str] = None
        if render_md:
            markdown_text = render_brief_strategy_markdown(strategy)
            markdown_hash = brief_strategy_sha256_hex(markdown_text.encode("utf-8"))

        meta = build_brief_strategy_meta(
            brief_hash=brief_hash,
            earnings_hash=earnings_hash,
            catalysts_hash=catalysts_hash,
            inputs_digest=inputs_digest,
            strategy_hash=strategy_hash,
            markdown_hash=markdown_hash,
            rows=rows_meta,
            cache_hit=bool(cache_hit),
        )
        meta_text = json.dumps(meta, indent=2, sort_keys=True)

        paths.strategy.write_bytes(strategy_bytes)
        paths.meta.write_text(meta_text, encoding="utf-8")
        if render_md and markdown_text is not None:
            paths.markdown.write_text(markdown_text, encoding="utf-8")

    out_path = Path(args.out)
    meta_out = Path(args.meta_out) if args.meta_out else out_path.with_suffix(
        out_path.suffix + ".meta.json"
    )
    _check_no_clobber(out_path, args.no_clobber)
    _check_no_clobber(meta_out, args.no_clobber)

    out_path.write_bytes(strategy_bytes)
    meta_out.write_text(meta_text, encoding="utf-8")

    if render_md and markdown_text is not None:
        md_path = Path(args.render_md)
        _check_no_clobber(md_path, args.no_clobber)
        md_path.write_text(markdown_text, encoding="utf-8")

    return 0


def _run_harness(cfg_path: Optional[str]) -> List[Dict[str, Any]]:
    from .tuning_harness import run_harness

    return run_harness(cfg_path)


def _run_harness_snapshots(cfg_path: Optional[str]) -> List[Dict[str, Any]]:
    from .tuning_harness import run_harness_snapshots

    return run_harness_snapshots(cfg_path)


def _write_tune_explain(args: argparse.Namespace, cfg_path: Optional[str]) -> None:
    cfg = _load_cfg(args.cfg)
    resolved_cfg = _resolve_cfg_path(args.cfg)
    cfg_source = resolved_cfg if resolved_cfg else "packaged"
    cfg_source_norm = cfg_source.replace("\\", "/")

    explain_dir = Path(args.explain_dir) if args.explain_dir else None
    if explain_dir:
        explain_dir.mkdir(parents=True, exist_ok=True)

    scenarios = _run_harness_snapshots(cfg_path)
    summaries = []
    config_hash = ""

    for entry in scenarios:
        scenario = entry["scenario"]
        metrics = entry["metrics"]
        snapshot = dict(entry["snapshot"])
        snapshot["snapshot_id"] = _deterministic_snapshot_id(snapshot)
        explain_payload = build_explain_payload(
            snapshot, metrics, cfg, cfg_source_norm, resolved_cfg
        )
        explain_payload["scenario"] = scenario
        explain_payload["snapshot"] = snapshot
        config_hash = str(explain_payload.get("config_hash", config_hash))

        explain_text = json.dumps(explain_payload, indent=2, sort_keys=True)
        if explain_dir:
            filename = f"{scenario}_{snapshot['snapshot_id']}.explain.json"
            _write_text(explain_dir / filename, explain_text, args.no_clobber)

        if args.explain:
            metrics_snapshot = snapshot.get("metrics_snapshot", {})
            breakdown = explain_payload.get("confidence_breakdown", {})
            summaries.append(
                {
                    "scenario": scenario,
                    "snapshot_id": snapshot.get("snapshot_id"),
                    "market_phase": snapshot.get("market_phase"),
                    "trend_regime": snapshot.get("trend_regime"),
                    "vol_regime": snapshot.get("vol_regime"),
                    "risk_tone": snapshot.get("risk_tone"),
                    "confidence": snapshot.get("confidence"),
                    "vote_disagreement_score": metrics_snapshot.get(
                        "vote_disagreement_score"
                    ),
                    "recent_change_window_days": metrics_snapshot.get(
                        "recent_change_window_days"
                    ),
                    "penalties": breakdown.get("penalties"),
                }
            )

    if args.explain:
        report = {
            "config_source": cfg_source_norm,
            "config_hash": config_hash,
            "scenario_count": len(summaries),
            "scenarios": summaries,
        }
        explain_report = json.dumps(report, indent=2, sort_keys=True)
        if args.explain == "-":
            print(explain_report)
        else:
            _write_text(Path(args.explain), explain_report, args.no_clobber)


def _run_replay_summary(cfg_path: Optional[str], prices_path: str) -> List[Dict[str, Any]]:
    cfg = _load_cfg(cfg_path or "")
    rows = _load_prices_csv(prices_path)
    dates = sorted({row.date for row in rows})
    if not dates:
        return []

    previous: Optional[RegimeSnapshot] = None
    days_since_change = 999
    summary_rows = []

    for current_date in dates:
        subset = [row for row in rows if row.date <= current_date]
        metrics = _build_metrics_safe(subset, cfg)
        reasoning = _normalize_reasoning([], f"Replay {current_date.isoformat()}")
        meta = {
            "as_of_ts": _as_of_ts(current_date),
            "session": "close",
            "engine_version": cfg.get("version", "regime_v1"),
            "universe": "US_EQ_ETF",
            "benchmarks": _parse_benchmarks("SPY,QQQ,IWM"),
            "reasoning": reasoning,
            "metrics_snapshot": {
                "recent_change_window_days": int(days_since_change),
            },
        }

        snapshot = build_regime_snapshot(metrics, meta, cfg, previous=previous)
        snapshot = _apply_deterministic_id(snapshot)
        summary_rows.append(
            {
                "source": "replay",
                "scenario": current_date.isoformat(),
                "market_phase": snapshot.market_phase,
                "trend_regime": snapshot.trend_regime,
                "vol_regime": snapshot.vol_regime,
                "risk_tone": snapshot.risk_tone,
                "confidence": snapshot.confidence,
                "vote_disagreement_score": snapshot.metrics_snapshot.vote_disagreement_score,
            }
        )

        if snapshot.regime_changed:
            days_since_change = 0
        else:
            days_since_change += 1
        previous = snapshot

    return summary_rows


def _determine_as_of_date(rows: Iterable[PriceRow], cfg: Dict[str, Any]) -> date:
    metrics_cfg = cfg.get("metrics", {})
    vix_ticker = str(metrics_cfg.get("vix_ticker", "VIX")).upper()
    required = set(
        str(t).upper()
        for t in metrics_cfg.get(
            "required_tickers", ["SPY", "TLT", "HYG", "LQD", vix_ticker]
        )
    )
    required.add(vix_ticker)

    dates_by_ticker: Dict[str, List[date]] = {}
    for row in rows:
        dates_by_ticker.setdefault(row.ticker, []).append(row.date)

    missing = sorted(required - set(dates_by_ticker))
    if missing:
        raise BadInputError(f"Missing required tickers: {', '.join(missing)}")

    latest_dates = [max(dates_by_ticker[ticker]) for ticker in required]
    return min(latest_dates)


def _build_snapshot_json(metrics: Dict[str, Any], meta: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    snapshot = build_regime_snapshot(metrics, meta, cfg, previous=None)
    snapshot = _apply_deterministic_id(snapshot)
    payload = _snapshot_to_dict(snapshot)
    return json.dumps(payload, sort_keys=True, indent=2)


def _load_prices_csv(path: str) -> List[PriceRow]:
    try:
        return read_prices_csv(path)
    except PricesIOError as exc:
        raise BadInputError(f"Prices CSV error: {exc}") from exc


def _build_metrics_safe(rows: Iterable[PriceRow], cfg: Dict[str, Any]) -> Dict[str, float]:
    try:
        return build_metrics_from_prices(rows_to_records(rows), cfg)
    except MetricsBuildError as exc:
        raise _classify_metrics_error(exc) from exc


def _normalize_reasoning(reasoning: List[str], label: str) -> List[str]:
    if not reasoning:
        reasoning = [label, "metrics_builder", "deterministic_inputs"]
    if len(reasoning) < 3:
        reasoning = reasoning + ["deterministic_inputs"] * (3 - len(reasoning))
    if len(reasoning) > 5:
        raise BadInputError("Reasoning must include at most 5 bullets.")
    return reasoning


def _parse_benchmarks(value: str) -> List[str]:
    benchmarks = [item.strip().upper() for item in value.split(",") if item.strip()]
    if not benchmarks:
        raise BadInputError("Benchmarks list cannot be empty.")
    return benchmarks


def _as_of_ts(value: date) -> str:
    return datetime.combine(value, datetime.min.time()).replace(tzinfo=None).isoformat() + "Z"


def _parse_date(value: str) -> date:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1]
    try:
        return datetime.fromisoformat(text).date()
    except ValueError as exc:
        raise BadInputError(f"Invalid date value: {value}") from exc


def _write_csv(rows: List[Dict[str, Any]], out_path: str, no_clobber: bool) -> None:
    if not rows:
        raise BadInputError("No rows to write.")
    fieldnames = list(rows[0].keys())
    for row in rows[1:]:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    if out_path:
        _check_no_clobber(Path(out_path), no_clobber)
        with open(out_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _resolve_cfg_path(cfg_path: str) -> Optional[str]:
    if cfg_path:
        return cfg_path
    return None


def _cfg_path_obj(cfg_path: str) -> Optional[Path]:
    if cfg_path:
        return Path(cfg_path)
    return None


def _resolve_store_dir(store_dir: str) -> str:
    if store_dir:
        return store_dir
    return os.environ.get("EDS_REGIME_STORE_DIR", "")


def _load_cfg(cfg_path: str) -> Dict[str, Any]:
    resolved = _resolve_cfg_path(cfg_path)
    if resolved:
        _debug(f"Using config: {resolved}")
    else:
        _debug("Using packaged config resource.")
    try:
        return validate_regime_config(load_regime_config(resolved))
    except (OSError, KeyError, ValueError) as exc:
        raise BadInputError(f"Config error: {exc}") from exc


def _classify_metrics_error(exc: MetricsBuildError) -> CliError:
    message = str(exc)
    if "Missing required tickers" in message:
        return BadInputError(message)
    if "Missing days" in message:
        return InsufficientDataError(message)
    if "Insufficient overlap" in message or "Insufficient history" in message:
        return InsufficientDataError(message)
    if "Missing data for" in message:
        return InsufficientDataError(message)
    return BadInputError(message)


def _check_no_clobber(path: Path, no_clobber: bool) -> None:
    if no_clobber and path.exists():
        raise BadInputError(f"Refusing to overwrite existing file: {path}")


def _write_text(path: Path, content: str, no_clobber: bool) -> None:
    _check_no_clobber(path, no_clobber)
    path.write_text(content, encoding="utf-8")


def _apply_deterministic_id(snapshot: RegimeSnapshot) -> RegimeSnapshot:
    payload = _snapshot_to_dict(snapshot)
    payload.pop("snapshot_id", None)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = sha256(raw.encode("utf-8")).hexdigest()[:32]
    return replace(snapshot, snapshot_id=digest)


def _deterministic_snapshot_id(payload: Dict[str, Any]) -> str:
    scrubbed = dict(payload)
    scrubbed.pop("snapshot_id", None)
    raw = json.dumps(scrubbed, sort_keys=True, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()[:32]


def _eprint(message: str) -> None:
    print(message, file=sys.stderr)


def _debug(message: str) -> None:
    if DEBUG:
        _eprint(message)


def _format_report(snapshot: Dict[str, Any]) -> str:
    metrics = snapshot.get("metrics_snapshot", {})
    votes = snapshot.get("signal_votes", {})

    metric_order = [
        "basket_price_above_50dma_pct",
        "basket_price_above_200dma_pct",
        "basket_ma50_slope_20d",
        "chop_score",
        "realized_vol_20d_pct",
        "vix_pct",
        "hyg_lqd_rs_20d",
        "spy_tlt_rs_20d",
        "recent_change_window_days",
        "vote_disagreement_score",
    ]

    trend_vote = votes.get("trend", {})
    vol_vote = votes.get("vol", {})
    risk_vote = votes.get("risk", {})

    lines = [
        f"Snapshot ID: {snapshot.get('snapshot_id')}",
        f"As Of: {snapshot.get('as_of_ts')}",
        f"Session: {snapshot.get('session')}",
        f"Market Phase: {snapshot.get('market_phase')}",
        f"Trend Regime: {snapshot.get('trend_regime')}",
        f"Vol Regime: {snapshot.get('vol_regime')}",
        f"Risk Tone: {snapshot.get('risk_tone')}",
        f"Confidence: {snapshot.get('confidence')}",
        "Signal Votes:",
        "  trend: "
        f"vote={trend_vote.get('vote')} "
        f"score={trend_vote.get('score')} "
        f"threshold={trend_vote.get('threshold')} "
        f"passed={trend_vote.get('passed')}",
        "  vol: "
        f"vote={vol_vote.get('vote')} "
        f"score={vol_vote.get('score')} "
        f"threshold={vol_vote.get('threshold')} "
        f"passed={vol_vote.get('passed')}",
        "  risk: "
        f"vote={risk_vote.get('vote')} "
        f"score={risk_vote.get('score')} "
        f"threshold={risk_vote.get('threshold')} "
        f"passed={risk_vote.get('passed')}",
        "Metrics:",
    ]

    for key in metric_order:
        if key in metrics:
            lines.append(f"  {key}: {metrics[key]}")

    extra_keys = sorted(key for key in metrics.keys() if key not in metric_order)
    for key in extra_keys:
        lines.append(f"  {key}: {metrics[key]}")

    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
