.PHONY: setup run-api run-ui test test-backend test-frontend acceptance e2e-synthetic real-datasets clean

PYTHON ?= .venv/bin/python
ifeq ($(OS),Windows_NT)
	PYTHON = .venv/Scripts/python.exe
endif

setup:
	python -m venv .venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.lock
	cp -n .env.example .env || copy .env.example .env || true
	cd dashboard && npm install

run-api:
	$(PYTHON) -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload

run-ui:
	cd dashboard && npm run dev

test: test-backend test-frontend

test-backend:
	$(PYTHON) -m pytest -q

test-frontend:
	cd dashboard && npm test -- --run

acceptance:
	$(PYTHON) -m pytest tests/test_stage10_scenarios.py -v

e2e-synthetic:
	$(PYTHON) scripts/run_e2e_synthetic.py

real-datasets:
	$(PYTHON) scripts/run_real_datasets.py
