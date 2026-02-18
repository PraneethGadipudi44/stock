from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Iterable, List

from core.regime.brief_adapter import inputs_hash as brief_inputs_hash

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
URL_RE = re.compile(r"^https://www\.sec\.gov/Archives/edgar/data/")


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _brief_paths() -> Dict[str, Path]:
    return {
        "brief": Path("tests/fixtures/brief_aapl_2024-02-15.json"),
        "brief_meta": Path("tests/fixtures/brief_aapl_2024-02-15.meta.json"),
    }


def _require_keys(obj: Dict[str, Any], keys: Iterable[str], label: str) -> None:
    missing = [k for k in keys if k not in obj]
    assert not missing, f"Missing {label} keys: {', '.join(missing)}"


def _sorted_by(items: List[Dict[str, Any]], keys: List[str]) -> List[Dict[str, Any]]:
    return sorted(items, key=lambda item: tuple(item.get(k, "") for k in keys))


def test_brief_sorted_ordering():
    paths = _brief_paths()
    brief = _load_json(paths["brief"])

    focus_list = brief.get("focus_list")
    assert isinstance(focus_list, list)
    expected_focus = sorted(
        focus_list, key=lambda item: (-float(item.get("score", 0.0)), item.get("ticker", ""))
    )
    assert focus_list == expected_focus

    price_moves = brief.get("price_moves")
    assert isinstance(price_moves, list)
    expected_moves = sorted(price_moves, key=lambda item: item.get("ticker", ""))
    assert price_moves == expected_moves

    today = brief.get("today_catalysts")
    recent = brief.get("recent_catalysts")
    assert isinstance(today, list)
    assert isinstance(recent, list)
    expected_today = _sorted_by(today, ["ticker", "event_date", "form", "accession_number"])
    expected_recent = _sorted_by(recent, ["ticker", "event_date", "form", "accession_number"])
    assert today == expected_today
    assert recent == expected_recent


def test_brief_required_keys_and_types():
    paths = _brief_paths()
    brief = _load_json(paths["brief"])

    _require_keys(
        brief,
        [
            "as_of",
            "focus_list",
            "today_catalysts",
            "recent_catalysts",
            "price_moves",
            "data_coverage",
        ],
        "brief",
    )
    assert isinstance(brief["as_of"], str)
    assert DATE_RE.match(brief["as_of"])

    for i, item in enumerate(brief["focus_list"]):
        assert isinstance(item, dict), f"focus_list[{i}] must be object"
        _require_keys(
            item,
            ["ticker", "score", "reasons", "has_catalyst_today", "has_recent_catalyst"],
            f"focus_list[{i}]",
        )
        assert isinstance(item["ticker"], str) and item["ticker"].strip()
        assert isinstance(item["score"], (int, float))
        assert isinstance(item["reasons"], list)
        assert 2 <= len(item["reasons"]) <= 5
        for reason in item["reasons"]:
            assert isinstance(reason, str) and reason.strip()
        assert isinstance(item["has_catalyst_today"], bool)
        assert isinstance(item["has_recent_catalyst"], bool)

    for i, item in enumerate(brief["price_moves"]):
        assert isinstance(item, dict), f"price_moves[{i}] must be object"
        _require_keys(item, ["ticker", "close", "pct_1d", "pct_5d"], f"price_moves[{i}]")
        assert isinstance(item["ticker"], str) and item["ticker"].strip()
        assert isinstance(item["close"], (int, float))
        assert item["pct_1d"] is None or isinstance(item["pct_1d"], (int, float))
        assert item["pct_5d"] is None or isinstance(item["pct_5d"], (int, float))

    for label in ("today_catalysts", "recent_catalysts"):
        for i, item in enumerate(brief[label]):
            assert isinstance(item, dict), f"{label}[{i}] must be object"
            _require_keys(
                item,
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
                f"{label}[{i}]",
            )
            assert isinstance(item["ticker"], str) and item["ticker"].strip()
            assert isinstance(item["event_date"], str) and DATE_RE.match(item["event_date"])
            assert isinstance(item["event_type"], str)
            assert isinstance(item["form"], str)
            assert isinstance(item["filing_date"], str) and DATE_RE.match(item["filing_date"])
            assert item["acceptance_datetime"] is None or isinstance(
                item["acceptance_datetime"], str
            )
            assert isinstance(item["accession_number"], str) and item["accession_number"].strip()
            assert isinstance(item["url_filing_detail"], str) and URL_RE.match(
                item["url_filing_detail"]
            )


def test_brief_no_duplicate_tickers():
    paths = _brief_paths()
    brief = _load_json(paths["brief"])

    focus_tickers = [str(item["ticker"]) for item in brief["focus_list"]]
    assert len(focus_tickers) == len(set(focus_tickers))

    price_tickers = [str(item["ticker"]) for item in brief["price_moves"]]
    assert len(price_tickers) == len(set(price_tickers))


def test_brief_coherence_and_coverage():
    paths = _brief_paths()
    brief = _load_json(paths["brief"])
    coverage = brief.get("data_coverage", {})

    focus_tickers = {str(item["ticker"]) for item in brief["focus_list"]}
    price_tickers = {str(item["ticker"]) for item in brief["price_moves"]}
    assert focus_tickers.issubset(price_tickers)

    assert isinstance(coverage.get("prices_rows"), int)
    assert coverage["prices_rows"] >= len(brief["price_moves"])

    for key in ("tickers_in_prices", "tickers_in_filings", "tickers_in_catalysts"):
        tickers = coverage.get(key, [])
        assert isinstance(tickers, list)
        assert tickers == sorted(tickers)


def test_brief_meta_hash_alignment():
    paths = _brief_paths()
    brief_path = paths["brief"]
    meta = _load_json(paths["brief_meta"])

    brief_bytes = brief_path.read_bytes()
    expected_brief_hash = sha256(brief_bytes).hexdigest()
    assert meta.get("normalized_brief_hash") == expected_brief_hash

    brief = _load_json(brief_path)
    as_of = brief["as_of"]
    assert isinstance(as_of, str) and DATE_RE.match(as_of)

    prices_hash = meta["inputs"]["prices"]["normalized_csv_hash"]
    filings_hash = meta["inputs"]["filings"]["normalized_jsonl_hash"]
    catalysts_hash = meta["inputs"]["catalysts"]["normalized_jsonl_hash"]

    expected_inputs = brief_inputs_hash(as_of, prices_hash, filings_hash, catalysts_hash)
    assert meta.get("inputs_hash") == expected_inputs

    md_hash = meta.get("markdown_hash")
    assert md_hash is None or (isinstance(md_hash, str) and re.match(r"^[a-f0-9]{64}$", md_hash))


def test_brief_asof_format_and_fixture_date():
    paths = _brief_paths()
    brief = _load_json(paths["brief"])
    assert brief["as_of"] == "2024-02-15"
    assert DATE_RE.match(brief["as_of"])


def test_brief_counts_sane_and_rows_match_meta():
    paths = _brief_paths()
    brief = _load_json(paths["brief"])
    meta = _load_json(paths["brief_meta"])

    rows = meta.get("rows", {})
    assert rows.get("focus_list") == len(brief["focus_list"])
    assert rows.get("today_catalysts") == len(brief["today_catalysts"])
    assert rows.get("recent_catalysts") == len(brief["recent_catalysts"])
    assert rows.get("price_moves") == len(brief["price_moves"])
