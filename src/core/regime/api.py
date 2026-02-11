from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .config import load_regime_config, validate_regime_config
from .engine import build_regime_snapshot
from .metrics_builder import MetricsBuildError, build_metrics_from_prices
from .prices_io import PricesIOError, read_prices_csv_text, rows_to_records
from .resources import default_config_path
from .run_snapshot import _snapshot_to_dict
from .store import JsonlSnapshotStore


class SnapshotRequest(BaseModel):
    prices: List[Dict[str, Any]]
    session: str = "close"
    benchmarks: List[str] = Field(default_factory=lambda: ["SPY", "QQQ", "IWM"])
    reasoning: List[str] = Field(
        default_factory=lambda: ["API snapshot", "metrics_builder", "deterministic"]
    )
    recent_change_window_days: int = 999
    inputs_hash: Optional[str] = None
    cfg_path: Optional[str] = None


def create_app(store_dir: Optional[str] = None) -> FastAPI:
    app = FastAPI(title="EDS Regime Engine", version="v1")
    store_dir = store_dir or os.environ.get("EDS_REGIME_STORE_DIR", "")

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/snapshot")
    async def snapshot_endpoint(
        file: UploadFile | None = File(default=None),
        session: str = Form(default="close"),
        benchmarks: str = Form(default="SPY,QQQ,IWM"),
        reasoning: str = Form(default=""),
        recent_change_window_days: int = Form(default=999),
        inputs_hash: str = Form(default=""),
        cfg_path: str = Form(default=""),
        body: SnapshotRequest | None = Body(default=None),
    ) -> JSONResponse:
        if file is None and body is None:
            raise HTTPException(status_code=400, detail="Provide CSV file or JSON body.")

        if file is not None:
            text = (await file.read()).decode("utf-8")
            try:
                rows = read_prices_csv_text(text)
            except PricesIOError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            prices_records = rows_to_records(rows)
            reasoning_list = _parse_reasoning(reasoning)
            meta = {
                "session": session,
                "benchmarks": _parse_benchmarks(benchmarks),
                "reasoning": reasoning_list,
                "metrics_snapshot": {
                    "recent_change_window_days": int(recent_change_window_days)
                },
            }
            if inputs_hash:
                meta["inputs_hash"] = inputs_hash
            cfg = _load_cfg(cfg_path)
            as_of_date = _latest_common_date_from_records(prices_records)
        else:
            prices_records = body.prices
            meta = {
                "session": body.session,
                "benchmarks": body.benchmarks,
                "reasoning": _normalize_reasoning(body.reasoning),
                "metrics_snapshot": {
                    "recent_change_window_days": int(body.recent_change_window_days)
                },
            }
            if body.inputs_hash:
                meta["inputs_hash"] = body.inputs_hash
            cfg = _load_cfg(body.cfg_path or cfg_path)
            as_of_date = _latest_common_date_from_records(prices_records)

        meta.update(
            {
                "as_of_ts": f"{as_of_date.isoformat()}T00:00:00Z",
                "engine_version": cfg.get("version", "regime_v1"),
                "universe": "US_EQ_ETF",
            }
        )

        try:
            metrics = build_metrics_from_prices(prices_records, cfg)
        except MetricsBuildError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        snapshot = build_regime_snapshot(metrics, meta, cfg)
        payload = _snapshot_to_dict(snapshot)

        if store_dir:
            store = JsonlSnapshotStore(
                Path(store_dir), cfg_path=_cfg_path_obj(cfg_path or default_config_path() or "")
            )
            store.append(json.dumps(payload, sort_keys=True, indent=2))

        return JSONResponse(content=payload)

    @app.get("/v1/latest")
    def latest_snapshot() -> JSONResponse:
        store = _require_store(store_dir)
        latest = store.latest()
        if latest is None:
            raise HTTPException(status_code=404, detail="No snapshots found.")
        return JSONResponse(content=latest)

    @app.get("/v1/snapshots/{snapshot_id}")
    def get_snapshot(snapshot_id: str) -> JSONResponse:
        store = _require_store(store_dir)
        entry = store.get(snapshot_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Snapshot not found.")
        return JSONResponse(content=entry)

    @app.get("/v1/history")
    def history(limit: int = 200) -> JSONResponse:
        store = _require_store(store_dir)
        entries = store.history(limit=limit)
        return JSONResponse(content=entries)

    return app


def _require_store(store_dir: str) -> JsonlSnapshotStore:
    if not store_dir:
        raise HTTPException(status_code=400, detail="Store directory not configured.")
    return JsonlSnapshotStore(Path(store_dir))


def _load_cfg(cfg_path: str) -> Dict[str, Any]:
    cfg = validate_regime_config(load_regime_config(cfg_path or None))
    return cfg


def _cfg_path_obj(cfg_path: str) -> Optional[Path]:
    if cfg_path:
        return Path(cfg_path)
    return None


def _parse_benchmarks(value: str) -> List[str]:
    if not value:
        return ["SPY", "QQQ", "IWM"]
    return [item.strip().upper() for item in value.split(",") if item.strip()]


def _parse_reasoning(value: str) -> List[str]:
    if not value:
        return ["API snapshot", "metrics_builder", "deterministic"]
    parts = [item.strip() for item in value.split(",") if item.strip()]
    return _normalize_reasoning(parts)


def _normalize_reasoning(reasoning: List[str]) -> List[str]:
    if len(reasoning) < 3:
        reasoning = reasoning + ["deterministic"] * (3 - len(reasoning))
    if len(reasoning) > 5:
        reasoning = reasoning[:5]
    return reasoning


def _latest_common_date_from_records(records: List[Dict[str, Any]]) -> date:
    dates_by_ticker: Dict[str, List[date]] = {}
    for row in records:
        ticker = str(row["ticker"]).upper().strip()
        row_date = row["date"]
        if isinstance(row_date, str):
            text = row_date.replace("Z", "")
            if "T" in text:
                row_date = date.fromisoformat(text.split("T")[0])
            else:
                row_date = date.fromisoformat(text)
        dates_by_ticker.setdefault(ticker, []).append(row_date)

    latest_dates = [max(dates) for dates in dates_by_ticker.values()]
    return min(latest_dates)
