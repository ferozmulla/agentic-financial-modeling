# Energy Model Onboarding Module (`model-onboarding`)

Automated, human-in-the-loop onboarding pipeline for Energy modeling spreadsheets (`.xlsx` / `.xlsm`), invokable either from **Cloudtop Cowork (`/onboard-energy-model-gcp`)** with zero local repo syncing or from the **Admin CLI (`onboard`)**.

## Three-Stage Architecture

1. **Stage 1 — Deterministic Hygiene Scan, Exception Report & Go/No-Go Gate (`hygiene_gate.py`)**:
   Wraps `portfolio-assessment` read-only to evaluate `MES` (`LES`), `MHS`, `MDR`, and `MRI`, surfacing a prioritized **Exception Report** (`BLOCKER`, `WARNING`, `INFO`) and a deterministic **`GO` / `CONDITIONAL_GO` / `NO_GO`** decision before spending sandbox compute.
2. **Stage 2 — Isolated Managed Agents Sandbox Builder (`sandbox_worker.py` + `sanitizer.py`)**:
   Mounts the staged workbook, extracted MS-OVBA LZNT1 VBA modules (`vba_extractor.py`), and the `energy-twin-builder` scaffold into Google Cloud's Managed Agents API (`antigravity-preview-05-2026`, `v1beta1`, `global`) with zero GCP admin or Git credentials. Generates `<model_slug>-bq-twin/` and runs an iterative `pytest` numeric parity loop against cached Excel baseline values, followed by local AST/path sanitization and an independent local `pytest` parity check.
3. **Stage 3 — Git PR Review Gate & Post-Approval Deployment (`pr_publisher.py` + `deployer.py`)**:
   Archives the seed workbook to the GCS Golden Vault, opens a GitHub Pull Request (via the repo-free GitHub Git Data REST API on Cloud Run, or an isolated `git worktree` on CLI) embedding the **Go/No-Go Scorecard**, **Hygiene Exception Report**, and **Parity Verification Report**, and—after human PR review—deploys the isolated BigQuery Digital Twin (`dt_*` + 4-Ws `dt_audit_events`), `ARIMA_PLUS` BQML forecasts, dedicated Cloud Run MCP server, and Agent Registry skills.

## One-Time Cloud Run + Cowork Setup (Repo-Free on Cloudtop)

```bash
# 1. Deploy model-onboarding-mcp to Cloud Run (from Mac / workstation once)
.venv/bin/python model-onboarding/scripts/deploy_onboarding_mcp.py --project-id comm-model-mod

# 2. Wire model-onboarding-mcp + /onboard-energy-model-gcp into Cowork (leaves Brazil & EULR untouched)
python3 model-onboarding/scripts/install_onboarding_cowork.py \
  --server-url "https://<model-onboarding-mcp-url>.a.run.app"
```

After that one-time setup, an Administrator in Cowork simply clicks **`+`** to attach a `.xlsx`/`.xlsm` file and types `/onboard-energy-model-gcp`.

## Admin CLI Quickstart

```bash
# Stage 1: Evaluate workbook hygiene, Exception Report, and Go/No-Go recommendation
.venv/bin/python model-onboarding/scripts/onboard.py assess \
  brazil-power-v13/seed/2023-11-27-Brazil_TT_v13_RJEB.xlsm \
  --output-dir /tmp/onboard_reports

# Stages 1 -> 2 -> 3a: Submit workbook for sandbox generation + local branch / GitHub PR
.venv/bin/python model-onboarding/scripts/onboard.py submit <workbook.xlsm> --slug <model-slug> [--local-branch-only]

# Stage 3b (Post-PR merge): Provision BigQuery + BQML + Cloud Run MCP + Agent Registry
.venv/bin/python model-onboarding/scripts/onboard.py deploy <model-slug> --pr-number <N> --require-merged-pr
```
