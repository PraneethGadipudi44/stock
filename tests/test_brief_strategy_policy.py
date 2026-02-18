from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from core.regime.brief_strategy_adapter import inputs_hash as strategy_inputs_hash

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _strategy_paths() -> Dict[str, Path]:
    return {
        "strategy": Path("tests/fixtures/brief_strategy_aapl_2024-02-15.json"),
        "strategy_meta": Path("tests/fixtures/brief_strategy_aapl_2024-02-15.meta.json"),
        "brief_meta": Path("tests/fixtures/brief_aapl_2024-02-15.meta.json"),
        "earnings_meta": Path("tests/fixtures/earnings_aapl_2024-02-01_2024-03-01.meta.json"),
        "catalysts_meta": Path(
            "tests/fixtures/catalysts_aapl_2024-02-01_2024-03-01.meta.json"
        ),
    }


def _require_keys(obj: Dict[str, Any], keys: List[str], label: str) -> None:
    missing = [k for k in keys if k not in obj]
    assert not missing, f"Missing {label} keys: {', '.join(missing)}"


def _priority_rank(value: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(str(value), 3)


def _signal_sort_key(sig: Dict[str, Any]) -> Tuple[int, float, str]:
    # priority asc (high first), score desc, ticker asc
    priority = _priority_rank(sig.get("priority"))
    score = float(sig.get("score", 0.0))
    ticker = str(sig.get("ticker", ""))
    return (priority, -score, ticker)


def test_strategy_sorted_ordering():
    paths = _strategy_paths()
    strategy = _load_json(paths["strategy"])

    signals = strategy.get("signals")
    assert isinstance(signals, list), "signals must be array"
    sorted_signals = sorted(signals, key=_signal_sort_key)
    assert signals == sorted_signals, (
        "signals must be sorted by (priority high->low, score desc, ticker asc)"
    )

    playbook = strategy.get("playbook")
    assert isinstance(playbook, dict), "playbook must be object"

    for key in ("watchlist", "event_risk", "momentum"):
        items = playbook.get(key)
        assert isinstance(items, list), f"playbook.{key} must be array"
        expected = sorted([str(x) for x in items])
        actual = [str(x) for x in items]
        assert actual == expected, f"playbook.{key} must be lexicographically sorted"


def test_strategy_required_keys_and_types():
    paths = _strategy_paths()
    strategy = _load_json(paths["strategy"])

    _require_keys(strategy, ["as_of", "signals", "playbook"], "strategy")
    assert isinstance(strategy["as_of"], str)
    assert DATE_RE.match(strategy["as_of"]), "strategy.as_of must be YYYY-MM-DD"

    signals = strategy["signals"]
    assert isinstance(signals, list)

    for i, sig in enumerate(signals):
        assert isinstance(sig, dict), f"signal[{i}] must be object"
        _require_keys(
            sig,
            ["ticker", "priority", "score", "tags", "summary", "inputs"],
            f"signal[{i}]",
        )

        assert isinstance(sig["ticker"], str)
        assert sig["ticker"].strip(), f"signal[{i}].ticker must be non-empty"

        assert isinstance(sig["priority"], str), f"signal[{i}].priority must be string"
        assert isinstance(sig["score"], (int, float)), f"signal[{i}].score must be number"

        tags = sig["tags"]
        assert isinstance(tags, list), f"signal[{i}].tags must be array"
        assert 1 <= len(tags) <= 5, f"signal[{i}].tags length must be 1..5"
        for t in tags:
            assert isinstance(t, str), f"signal[{i}].tags items must be strings"
            assert t.strip(), f"signal[{i}].tags items must be non-empty"

        summary = sig["summary"]
        assert isinstance(summary, str), f"signal[{i}].summary must be string"
        assert 20 <= len(summary) <= 240, (
            f"signal[{i}].summary length must be 20..240"
        )

        inputs = sig["inputs"]
        assert isinstance(inputs, dict), f"signal[{i}].inputs must be object"
        _require_keys(
            inputs,
            [
                "pct_1d",
                "has_catalyst_today",
                "has_recent_catalyst",
                "has_earnings_within_5d",
                "earnings_event_date",
            ],
            f"signal[{i}].inputs",
        )
        assert inputs["pct_1d"] is None or isinstance(inputs["pct_1d"], (int, float))
        assert isinstance(inputs["has_catalyst_today"], bool)
        assert isinstance(inputs["has_recent_catalyst"], bool)
        assert isinstance(inputs["has_earnings_within_5d"], bool)
        assert inputs["earnings_event_date"] is None or isinstance(
            inputs["earnings_event_date"], str
        )


def test_strategy_no_duplicates():
    paths = _strategy_paths()
    strategy = _load_json(paths["strategy"])

    signals = strategy["signals"]
    tickers = [str(s["ticker"]) for s in signals]
    assert len(tickers) == len(set(tickers)), "No duplicate tickers allowed in signals"

    playbook = strategy["playbook"]
    for key in ("watchlist", "event_risk", "momentum"):
        items = [str(x) for x in playbook.get(key, [])]
        assert len(items) == len(
            set(items)
        ), f"playbook.{key} must contain unique tickers"


def test_strategy_playbook_coherence_and_counts():
    paths = _strategy_paths()
    strategy = _load_json(paths["strategy"])
    meta = _load_json(paths["strategy_meta"])

    signals = strategy["signals"]
    signal_tickers: Set[str] = {str(s["ticker"]) for s in signals}

    playbook = strategy["playbook"]
    for key in ("watchlist", "event_risk", "momentum"):
        items = [str(x) for x in playbook.get(key, [])]
        missing = [t for t in items if t not in signal_tickers]
        assert not missing, f"playbook.{key} tickers must exist in signals: {missing}"

    rows = meta.get("rows", {})
    assert rows.get("signals") == len(signals), "meta.rows.signals must equal len(signals)"
    assert rows.get("playbook_watchlist") == len(playbook.get("watchlist", []))
    assert rows.get("playbook_event_risk") == len(playbook.get("event_risk", []))
    assert rows.get("playbook_momentum") == len(playbook.get("momentum", []))


def test_strategy_asof_format_and_fixture_date():
    paths = _strategy_paths()
    strategy = _load_json(paths["strategy"])
    assert strategy["as_of"] == "2024-02-15", "fixture strategy.as_of must match expected fixture date"
    assert DATE_RE.match(strategy["as_of"]), "strategy.as_of must be YYYY-MM-DD"


def test_strategy_meta_hash_alignment():
    paths = _strategy_paths()
    strategy_path = paths["strategy"]
    meta = _load_json(paths["strategy_meta"])

    strategy_bytes = strategy_path.read_bytes()
    expected_strategy_hash = sha256(strategy_bytes).hexdigest()
    assert meta.get("normalized_strategy_hash") == expected_strategy_hash

    strategy = _load_json(strategy_path)
    as_of = strategy["as_of"]
    assert isinstance(as_of, str) and DATE_RE.match(as_of)

    brief_meta = _load_json(paths["brief_meta"])
    earnings_meta = _load_json(paths["earnings_meta"])
    catalysts_meta = _load_json(paths["catalysts_meta"])

    brief_hash = brief_meta["normalized_brief_hash"]
    earnings_hash = earnings_meta["normalized_jsonl_hash"]
    catalysts_hash = catalysts_meta["normalized_jsonl_hash"]

    expected_inputs = strategy_inputs_hash(as_of, brief_hash, earnings_hash, catalysts_hash)
    assert meta.get("inputs_hash") == expected_inputs

    md_hash = meta.get("markdown_hash")
    assert md_hash is None or (isinstance(md_hash, str) and re.match(r"^[a-f0-9]{64}$", md_hash))


def test_strategy_counts_sane():
    paths = _strategy_paths()
    strategy = _load_json(paths["strategy"])

    playbook = strategy["playbook"]
    assert len(playbook.get("watchlist", [])) <= 10, "playbook.watchlist length must be <= 10"

    assert len(strategy["signals"]) >= 0
    for key in ("watchlist", "event_risk", "momentum"):
        assert len(playbook.get(key, [])) >= 0
