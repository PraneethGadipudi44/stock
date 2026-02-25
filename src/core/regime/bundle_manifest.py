from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

from .verify_manifest import verify_manifest


FIXED_ZIP_DATE = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class BundleEntry:
    name: str
    path: Path


def _zip_entry(name: str, data: bytes, zf: zipfile.ZipFile) -> None:
    info = zipfile.ZipInfo(filename=name, date_time=FIXED_ZIP_DATE)
    info.compress_type = zipfile.ZIP_STORED
    zf.writestr(info, data)


def _entry_list(
    *,
    manifest: Path,
    manifest_meta: Path,
    brief: Path,
    brief_meta: Path,
    strategy: Path,
    strategy_meta: Path,
    trace: Path,
    trace_meta: Path,
    diff_strategy: Path,
    diff_strategy_meta: Path,
    diff_trace: Path,
    diff_trace_meta: Path,
    strategy_md: Optional[Path],
    diff_strategy_md: Optional[Path],
    diff_trace_md: Optional[Path],
) -> Sequence[BundleEntry]:
    entries = [
        BundleEntry("manifest.json", manifest),
        BundleEntry("manifest.meta.json", manifest_meta),
        BundleEntry("brief.json", brief),
        BundleEntry("brief.meta.json", brief_meta),
        BundleEntry("strategy.json", strategy),
        BundleEntry("strategy.meta.json", strategy_meta),
        BundleEntry("trace.json", trace),
        BundleEntry("trace.meta.json", trace_meta),
        BundleEntry("diff_strategy.json", diff_strategy),
        BundleEntry("diff_strategy.meta.json", diff_strategy_meta),
        BundleEntry("diff_trace.json", diff_trace),
        BundleEntry("diff_trace.meta.json", diff_trace_meta),
    ]
    if strategy_md is not None:
        entries.append(BundleEntry("strategy.md", strategy_md))
    if diff_strategy_md is not None:
        entries.append(BundleEntry("diff_strategy.md", diff_strategy_md))
    if diff_trace_md is not None:
        entries.append(BundleEntry("diff_trace.md", diff_trace_md))
    return entries


def bundle_manifest(
    *,
    manifest: Path,
    manifest_meta: Path,
    brief: Path,
    brief_meta: Path,
    strategy: Path,
    strategy_meta: Path,
    trace: Path,
    trace_meta: Path,
    diff_strategy: Path,
    diff_strategy_meta: Path,
    diff_trace: Path,
    diff_trace_meta: Path,
    out_path: Path,
    as_of: Optional[str] = None,
    strategy_md: Optional[Path] = None,
    diff_strategy_md: Optional[Path] = None,
    diff_trace_md: Optional[Path] = None,
) -> None:
    verify_manifest(
        manifest_path=manifest,
        manifest_meta_path=manifest_meta,
        brief_path=brief,
        brief_meta_path=brief_meta,
        strategy_path=strategy,
        strategy_meta_path=strategy_meta,
        trace_path=trace,
        trace_meta_path=trace_meta,
        diff_strategy_path=diff_strategy,
        diff_strategy_meta_path=diff_strategy_meta,
        diff_trace_path=diff_trace,
        diff_trace_meta_path=diff_trace_meta,
        as_of=as_of,
        strategy_md_path=strategy_md,
        diff_strategy_md_path=diff_strategy_md,
        diff_trace_md_path=diff_trace_md,
        write_report=False,
    )

    entries = _entry_list(
        manifest=manifest,
        manifest_meta=manifest_meta,
        brief=brief,
        brief_meta=brief_meta,
        strategy=strategy,
        strategy_meta=strategy_meta,
        trace=trace,
        trace_meta=trace_meta,
        diff_strategy=diff_strategy,
        diff_strategy_meta=diff_strategy_meta,
        diff_trace=diff_trace,
        diff_trace_meta=diff_trace_meta,
        strategy_md=strategy_md,
        diff_strategy_md=diff_strategy_md,
        diff_trace_md=diff_trace_md,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w") as zf:
        for entry in entries:
            _zip_entry(entry.name, entry.path.read_bytes(), zf)


def expected_bundle_entries(
    *,
    strategy_md: Optional[Path],
    diff_strategy_md: Optional[Path],
    diff_trace_md: Optional[Path],
) -> list[str]:
    entries = [
        "manifest.json",
        "manifest.meta.json",
        "brief.json",
        "brief.meta.json",
        "strategy.json",
        "strategy.meta.json",
        "trace.json",
        "trace.meta.json",
        "diff_strategy.json",
        "diff_strategy.meta.json",
        "diff_trace.json",
        "diff_trace.meta.json",
    ]
    if strategy_md is not None:
        entries.append("strategy.md")
    if diff_strategy_md is not None:
        entries.append("diff_strategy.md")
    if diff_trace_md is not None:
        entries.append("diff_trace.md")
    return entries
