UV ?= uv
PY ?= python3

.PHONY: setup setup-auditor test demo report verify

setup: setup-auditor
	$(UV) sync --python 3.12
	@test -f .env || cp .env.example .env
	$(UV) run python scripts/fill_env.py

setup-auditor:
	$(PY) scripts/setup_auditor.py

test:
	$(UV) run pytest

demo:
	$(UV) run firedrill run-demo --offline

report:
	$(UV) run firedrill report

verify:
	$(UV) run firedrill verify
