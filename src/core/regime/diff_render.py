from __future__ import annotations

from typing import Any, Dict, Iterable, List


def _bool_flag(value: bool) -> str:
    return "true" if bool(value) else "false"


def _signed(value: int) -> str:
    return f"{value:+d}"


def _lines(title: str, lines: Iterable[str]) -> List[str]:
    output = [title]
    output.extend(lines)
    output.append("")
    return output


def render_brief_strategy_diff(diff_payload: Dict[str, Any]) -> str:
    right_as_of = diff_payload["right"]["as_of"]
    lines: List[str] = [f"# Strategy Diff ({right_as_of})", ""]

    summary = diff_payload.get("summary") or []
    lines.extend(_lines("## Summary", [f"- {line}" for line in summary]))

    changes = diff_payload["changes"]
    lines.extend(
        _lines(
            "## Changes",
            [
                f"- as_of_changed: {_bool_flag(changes['as_of_changed'])}",
                f"- strategy_changed: {_bool_flag(changes['strategy_changed'])}",
                f"- markdown_changed: {_bool_flag(changes['markdown_changed'])}",
            ],
        )
    )

    coverage = diff_payload["coverage_delta"]
    lines.extend(
        _lines(
            "## Coverage Delta",
            [
                f"- signals: {_signed(coverage['signals_delta'])}",
                f"- watchlist: {_signed(coverage['watchlist_delta'])}",
                f"- event_risk: {_signed(coverage['event_risk_delta'])}",
                f"- momentum: {_signed(coverage['momentum_delta'])}",
            ],
        )
    )

    left = diff_payload["left"]
    right = diff_payload["right"]
    lines.extend(
        _lines(
            "## Hashes",
            [
                f"- left.inputs_hash: {left['inputs_hash']}",
                f"- right.inputs_hash: {right['inputs_hash']}",
                f"- inputs_hash: {diff_payload['inputs_hash']}",
            ],
        )
    )

    return "\n".join(lines) + "\n"


def _synthesize_trace_summary(diff_payload: Dict[str, Any]) -> List[str]:
    left = diff_payload["left"]
    right = diff_payload["right"]
    coverage = diff_payload["coverage_delta"]
    return [
        f"as_of: {left['as_of']} -> {right['as_of']}",
        (
            "coverage: "
            f"signals {_signed(coverage['signals_rows_delta'])}, "
            f"watchlist {_signed(coverage['playbook_watchlist_delta'])}, "
            f"event_risk {_signed(coverage['playbook_event_risk_delta'])}, "
            f"momentum {_signed(coverage['playbook_momentum_delta'])}"
        ),
    ]


def render_trace_strategy_brief_diff(diff_payload: Dict[str, Any]) -> str:
    right_as_of = diff_payload["right"]["as_of"]
    lines: List[str] = [f"# Trace Diff ({right_as_of})", ""]

    summary = diff_payload.get("summary")
    if not summary:
        summary = _synthesize_trace_summary(diff_payload)
    lines.extend(_lines("## Summary", [f"- {line}" for line in summary]))

    changes = diff_payload["changes"]
    lines.extend(
        _lines(
            "## Changes",
            [
                f"- as_of_changed: {_bool_flag(changes['as_of_changed'])}",
                f"- brief_changed: {_bool_flag(changes['brief_changed'])}",
                f"- earnings_changed: {_bool_flag(changes['earnings_changed'])}",
                f"- catalysts_changed: {_bool_flag(changes['catalysts_changed'])}",
                f"- strategy_changed: {_bool_flag(changes['strategy_changed'])}",
                f"- markdown_changed: {_bool_flag(changes['markdown_changed'])}",
                f"- trace_changed: {_bool_flag(changes['trace_changed'])}",
            ],
        )
    )

    coverage = diff_payload["coverage_delta"]
    lines.extend(
        _lines(
            "## Coverage Delta",
            [
                f"- signals: {_signed(coverage['signals_rows_delta'])}",
                f"- watchlist: {_signed(coverage['playbook_watchlist_delta'])}",
                f"- event_risk: {_signed(coverage['playbook_event_risk_delta'])}",
                f"- momentum: {_signed(coverage['playbook_momentum_delta'])}",
            ],
        )
    )

    left = diff_payload["left"]
    right = diff_payload["right"]
    lines.extend(
        _lines(
            "## Hashes",
            [
                f"- left.inputs_hash: {left['inputs_hash']}",
                f"- right.inputs_hash: {right['inputs_hash']}",
                f"- inputs_hash: {diff_payload['inputs_hash']}",
            ],
        )
    )

    return "\n".join(lines) + "\n"
