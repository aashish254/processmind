.PHONY: setup test demo eval research-eval discover-im clean serve lint-check

PY := ./.venv/bin/python

setup:
	/opt/homebrew/bin/python3.11 -m venv --system-site-packages .venv || python3 -m venv .venv
	./.venv/bin/pip install --quiet --upgrade pip
	./.venv/bin/pip install --quiet -e ".[graph,api,dev]"

test:
	$(PY) -m pytest

demo:
	$(PY) -m process_miner.cli demo -o outputs/demo
	$(PY) -m process_miner.cli eval -o outputs/eval
	@echo "Open outputs/demo/*_report.html for the analyst reports."

eval:
	$(PY) -m process_miner.cli eval -o outputs/eval

serve:
	$(PY) -m process_miner.cli serve --port 8000

logs:
	$(PY) scripts/generate_logs.py

clean:
	rm -rf outputs/demo outputs/eval outputs/_tests .pytest_cache
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

research-eval:
	$(PY) -m process_miner.cli research-eval

discover-im:
	$(PY) -m process_miner.cli discover-im inputs/it_incident_events.csv -o outputs/im
