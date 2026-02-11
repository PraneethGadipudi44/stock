from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from core.regime.tuning_harness import run_harness


def main() -> int:
    parser = argparse.ArgumentParser(description="Regime v1 tuning harness")
    parser.add_argument(
        "--cfg",
        default="",
        help="Path to regime config file. Defaults to packaged config if empty.",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Optional CSV output path. Defaults to stdout if empty.",
    )
    args = parser.parse_args()

    rows = run_harness(args.cfg or None)

    fieldnames = list(rows[0].keys()) if rows else []

    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
