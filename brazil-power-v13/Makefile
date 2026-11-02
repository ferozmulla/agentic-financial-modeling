.PHONY: setup extract-fixtures test test-unit test-integration test-e2e test-infra lint run-local seed-sheet tf-init tf-validate tf-plan tf-apply tf-destroy

VENV_DIR := $(shell if [ -d .venv ]; then echo .venv; else echo ../.venv; fi)
PYTHON := $(VENV_DIR)/bin/python
PYTEST := $(VENV_DIR)/bin/pytest
RUFF := $(VENV_DIR)/bin/ruff
UVICORN := $(VENV_DIR)/bin/uvicorn
GCP_PROJECT_ID ?= comm-model-mod
GCP_REGION ?= us-central1
GEMINI_LOCATION ?= us

setup:
	python3 -m venv $(VENV_DIR)
	$(VENV_DIR)/bin/pip install --upgrade pip
	$(VENV_DIR)/bin/pip install -r requirements-dev.txt

extract-fixtures:
	PYTHONPATH=. $(PYTHON) -m src.cli.extract_baseline_fixtures

test:
	$(PYTEST) -v

test-unit:
	$(PYTEST) tests/unit -v

test-integration:
	$(PYTEST) tests/integration -v

test-e2e:
	$(PYTEST) tests/e2e -v

test-infra:
	$(PYTEST) tests/infra -v

lint:
	$(RUFF) check src tests scripts

run-local:
	ENV=local PYTHONPATH=. $(UVICORN) src.api.main:app --host 127.0.0.1 --port 8000 --reload

seed-sheet:
	PYTHONPATH=. $(PYTHON) scripts/seed_google_sheet_from_xlsm.py --project-id $(GCP_PROJECT_ID)

tf-init:
	terraform -chdir=infra/terraform init -backend=false

tf-validate:
	terraform -chdir=infra/terraform validate

tf-plan:
	terraform -chdir=infra/terraform plan -var="project_id=$(GCP_PROJECT_ID)" -var="region=$(GCP_REGION)"

tf-apply:
	terraform -chdir=infra/terraform apply -auto-approve -var="project_id=$(GCP_PROJECT_ID)" -var="region=$(GCP_REGION)"

tf-destroy:
	terraform -chdir=infra/terraform destroy -auto-approve -var="project_id=$(GCP_PROJECT_ID)" -var="region=$(GCP_REGION)"
