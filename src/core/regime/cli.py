from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .config import load_regime_config, validate_regime_config
from .engine import build_regime_snapshot
from .metrics_builder import MetricsBuildError, build_metrics_from_prices
from .models import RegimeSnapshot
from .prices_io import PriceRow, PricesIOError, read_prices_csv, rows_to_records
from .resources import default_config_path
from .run_snapshot import _snapshot_to_dict
from .store import JsonlSnapshotStore


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Regime Engine CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot_parser = subparsers.add_parser("snapshot", help="Build a regime snapshot")
    snapshot_parser.add_argument("--cfg", default="", help="Path to regime config")
    snapshot_parser.add_argument("--prices", required=True, help="Path to prices CSV")
    snapshot_parser.add_argument("--out", default="", help="Optional output JSON path")
    snapshot_parser.add_argument("--store", default="", help="Optional store directory")
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
        "--out", required=True, help="Output CSV path for tuning results"
    )

    report_parser = subparsers.add_parser("report", help="Render a snapshot summary")
    report_parser.add_argument(
        "--snapshot", default="", help="Path to snapshot JSON file"
    )
    report_parser.add_argument(
        "--store", default="", help="Store directory (uses latest.json)"
    )

    args = parser.parse_args(argv)

    if args.command == "snapshot":
        return _run_snapshot(args)
    if args.command == "replay":
        return _run_replay(args)
    if args.command == "tune":
        return _run_tune(args)
    if args.command == "report":
        return _run_report(args)
    return 1


def _run_snapshot(args: argparse.Namespace) -> int:
    cfg = validate_regime_config(load_regime_config(_resolve_cfg_path(args.cfg)))
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

    if args.out:
        Path(args.out).write_text(snapshot_json, encoding="utf-8")
    else:
        print(snapshot_json)

    store_dir = _resolve_store_dir(args.store)
    if store_dir:
        store = JsonlSnapshotStore(Path(store_dir), cfg_path=_cfg_path_obj(args.cfg))
        store.append(snapshot_json)

    return 0


def _run_replay(args: argparse.Namespace) -> int:
    cfg = validate_regime_config(load_regime_config(_resolve_cfg_path(args.cfg)))
    rows = _load_prices_csv(args.prices)

    start = _parse_date(args.start)
    end = _parse_date(args.end)
    if start > end:
        raise SystemExit("Start date must be <= end date.")

    dates = sorted({row.date for row in rows if start <= row.date <= end})
    if not dates:
        raise SystemExit("No prices within the requested date range.")

    store_dir = _resolve_store_dir(args.store)
    if not store_dir:
        raise SystemExit("Store directory is required for replay.")
    store = JsonlSnapshotStore(Path(store_dir), cfg_path=_cfg_path_obj(args.cfg))
    summary_rows = []

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
        payload = _snapshot_to_dict(snapshot)
        snapshot_json = json.dumps(payload, sort_keys=True, indent=2)
        store.append(snapshot_json)

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

    _write_csv(summary_rows, args.out)
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

    _write_csv(rows, args.out)
    return 0


def _run_report(args: argparse.Namespace) -> int:
    if args.snapshot:
        snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    else:
        store_dir = _resolve_store_dir(args.store)
        if not store_dir:
            raise SystemExit("Provide --snapshot or set --store / EDS_REGIME_STORE_DIR.")
        store = JsonlSnapshotStore(Path(store_dir))
        latest = store.latest()
        if latest is None:
            raise SystemExit("No snapshots found in store.")
        snapshot = latest["snapshot"]

    report = _format_report(snapshot)
    print(report)
    return 0


def _run_harness(cfg_path: Optional[str]) -> List[Dict[str, Any]]:
    from .tuning_harness import run_harness

    return run_harness(cfg_path)


def _run_replay_summary(cfg_path: Optional[str], prices_path: str) -> List[Dict[str, Any]]:
    cfg = validate_regime_config(load_regime_config(cfg_path))
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
        raise SystemExit(f"Missing required tickers: {', '.join(missing)}")

    latest_dates = [max(dates_by_ticker[ticker]) for ticker in required]
    return min(latest_dates)


def _build_snapshot_json(metrics: Dict[str, Any], meta: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    snapshot = build_regime_snapshot(metrics, meta, cfg, previous=None)
    payload = _snapshot_to_dict(snapshot)
    return json.dumps(payload, sort_keys=True, indent=2)


def _load_prices_csv(path: str) -> List[PriceRow]:
    try:
        return read_prices_csv(path)
    except PricesIOError as exc:
        raise SystemExit(f"Prices CSV error: {exc}") from exc


def _build_metrics_safe(rows: Iterable[PriceRow], cfg: Dict[str, Any]) -> Dict[str, float]:
    try:
        return build_metrics_from_prices(rows_to_records(rows), cfg)
    except MetricsBuildError as exc:
        raise SystemExit(f"Metrics build failed: {exc}") from exc


def _normalize_reasoning(reasoning: List[str], label: str) -> List[str]:
    if not reasoning:
        reasoning = [label, "metrics_builder", "deterministic_inputs"]
    if len(reasoning) < 3:
        reasoning = reasoning + ["deterministic_inputs"] * (3 - len(reasoning))
    if len(reasoning) > 5:
        raise SystemExit("Reasoning must include at most 5 bullets.")
    return reasoning


def _parse_benchmarks(value: str) -> List[str]:
    benchmarks = [item.strip().upper() for item in value.split(",") if item.strip()]
    if not benchmarks:
        raise SystemExit("Benchmarks list cannot be empty.")
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
        raise SystemExit(f"Invalid date value: {value}") from exc


def _write_csv(rows: List[Dict[str, Any]], out_path: str) -> None:
    if not rows:
        raise SystemExit("No rows to write.")
    fieldnames = list(rows[0].keys())
    for row in rows[1:]:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    if out_path:
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
    return default_config_path()


def _cfg_path_obj(cfg_path: str) -> Optional[Path]:
    if cfg_path:
        return Path(cfg_path)
    return None


def _resolve_store_dir(store_dir: str) -> str:
    if store_dir:
        return store_dir
    return os.environ.get("EDS_REGIME_STORE_DIR", "")


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
