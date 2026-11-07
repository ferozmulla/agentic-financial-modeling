.PHONY: setup extract-fixtures test lint run-local seed-sheet deploy-bqml tf-init tf-validate tf-plan tf-apply

VENV_DIR := $(shell if [ -d .venv ]; then echo .venv; else echo ../.venv; fi)
PYTHON := $(VENV_DIR)/bin/python
PYTEST := $(VENV_DIR)/bin/pytest
RUFF := $(VENV_DIR)/bin/ruff
UVICORN := $(VENV_DIR)/bin/uvicorn
GCP_PROJECT_ID ?= comm-model-mod
GCP_REGION ?= us-central1
GEMINI_LOCATION ?= us

setup:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements-dev.txt

extract-fixtures:
	PYTHONPATH=. $(PYTHON) -m src.cli.extract_eulr_seed

test:
	PYTHONPATH=. $(PYTEST) -v

lint:
	$(RUFF) check src tests scripts

run-local:
	ENV=local PYTHONPATH=. $(UVICORN) src.api.main:app --host 127.0.0.1 --port 8001 --reload

seed-sheet:
	PYTHONPATH=. $(PYTHON) scripts/push_sheets_live.py --project-id $(GCP_PROJECT_ID)

deploy-bqml:
	PYTHONPATH=. $(PYTHON) scripts/deploy_bqml_and_vertex.py --project-id $(GCP_PROJECT_ID)

tf-init:
	terraform -chdir=infra/terraform init -backend=false

tf-validate:
	terraform -chdir=infra/terraform validate

tf-plan:
	terraform -chdir=infra/terraform plan -var="project_id=$(GCP_PROJECT_ID)" -var="region=$(GCP_REGION)"

tf-apply:
	terraform -chdir=infra/terraform apply -auto-approve -var="project_id=$(GCP_PROJECT_ID)" -var="region=$(GCP_REGION)"
