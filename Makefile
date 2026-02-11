.PHONY: format lint test typecheck build tune

format:
	python -m black src tests
	python -m ruff check --fix src tests

lint:
	python -m ruff check src tests

test:
	python -m pytest -q

typecheck:
	python -m mypy src

build:
	python -m build

tune:
	python scripts/regime_tuning_harness.py --out data/tuning.csv
	python -c "from pathlib import Path; Path('data/store').mkdir(parents=True, exist_ok=True)"
	eds-regime replay --cfg config/regime_v1.yaml --prices tests/fixtures/prices_replay_long.csv --store data/store --start 2026-01-16 --end 2026-01-20 --out data/replay_summary.csv
