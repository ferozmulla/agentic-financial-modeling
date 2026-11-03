.PHONY: lint test run

VENV_DIR := $(shell if [ -d .venv ]; then echo .venv; elif [ -d ../.venv ]; then echo ../.venv; else echo ""; fi)
PYTHON := $(if $(VENV_DIR),$(VENV_DIR)/bin/python,python3)
PYTEST := $(if $(VENV_DIR),$(VENV_DIR)/bin/pytest,python3 -m pytest)
RUFF := $(if $(VENV_DIR),$(VENV_DIR)/bin/ruff,python3 -m ruff)

lint:
	$(RUFF) check src tests

test:
	$(PYTEST) -v

run:
	PYTHONPATH=src $(PYTHON) -m portfolio_assessment.cli
