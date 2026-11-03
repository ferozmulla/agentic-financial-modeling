.PHONY: lint test run

VENV_DIR := $(shell if [ -d .venv ]; then echo .venv; else echo ../.venv; fi)
PYTHON := $(VENV_DIR)/bin/python
PYTEST := $(VENV_DIR)/bin/pytest
RUFF := $(VENV_DIR)/bin/ruff

lint:
	$(RUFF) check src tests

test:
	$(PYTEST) -v

run:
	PYTHONPATH=src $(PYTHON) -m portfolio_assessment.cli
