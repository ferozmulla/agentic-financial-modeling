---
name: onboard-energy-model-gcp
description: "Administrator Human-in-the-Loop workflow for onboarding a new Energy modeling spreadsheet (.xlsx/.xlsm) in Cowork or Gemini Agent via model-onboarding-mcp: automatically stages `+`-attached session workbooks to GCS, runs the deterministic MES/MDR Hygiene & Exception Gate (GO / CONDITIONAL_GO / NO_GO), launches the isolated Managed Agents parity builder, opens a reviewable GitHub Pull Request, and deploys approved models to BigQuery, BQML, Cloud Run, and Agent Registry."
---

# Energy Spreadsheet Onboarding Workflow (`/onboard-energy-model-gcp`)

Use this skill whenever an Administrator invokes `/onboard-energy-model-gcp` or attaches a `.xlsx` / `.xlsm` Energy modeling spreadsheet in a Cowork session to onboard it into the platform.

## Dual-Mode Backend Invocation
1. **Mode A — Native Cowork MCP Connector (`model-onboarding-mcp`)**: Call `create_workbook_upload_url`, `assess_workbook_onboarding_readiness`, `start_workbook_onboarding_job`, `get_onboarding_job_status`, and `deploy_approved_onboarding_model` directly.
2. **Mode B — Direct Cloud Run HTTPS Fallback** (when native MCP tools are not bound yet):
   ```bash
   python3 -c '
   import json, os, sys, urllib.request
   url, tool, args = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
   body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": args}}).encode()
   hdrs = {"Content-Type": "application/json"}
   if os.getenv("ONBOARD_API_BEARER_TOKEN"):
       hdrs["Authorization"] = f"Bearer {os.environ[\"ONBOARD_API_BEARER_TOKEN\"]}"
   req = urllib.request.Request(f"{url.rstrip(\"/\")}/mcp", data=body, headers=hdrs, method="POST")
   resp = json.loads(urllib.request.urlopen(req, timeout=90).read().decode())
   print(resp["result"]["content"][0]["text"])
   ' "${ONBOARD_MCP_URL:-https://model-onboarding-mcp-2wcxwkmdga-uc.a.run.app}" "<tool_name>" '<json_args>'
   ```

---

## Workflow Steps

### Step 0: Automatic `+` Session File Upload (Zero Manual GCS Needed)
If the Administrator attached a `.xlsx` or `.xlsm` file directly to the Cowork session via **`+`** (so you see a local session path rather than a `gs://...` URI):
1. Call `create_workbook_upload_url(filename="<attached_basename.xlsm>")` on `model-onboarding-mcp`.
2. Stream the raw binary file from the Cowork session filesystem to cloud staging without reading binary bytes into prompt context:
   ```bash
   python3 -c '
   import json, os, pathlib, sys, urllib.request
   local_file, signed_put, direct_post, ctype = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
   data = pathlib.Path(local_file).read_bytes()
   if signed_put:
       req = urllib.request.Request(signed_put, data=data, headers={"Content-Type": ctype}, method="PUT")
       urllib.request.urlopen(req, timeout=120).read()
       print("UPLOADED_VIA_SIGNED_PUT")
   else:
       hdrs = {"Content-Type": "application/octet-stream"}
       if os.getenv("ONBOARD_API_BEARER_TOKEN"):
           hdrs["Authorization"] = f"Bearer {os.environ[\"ONBOARD_API_BEARER_TOKEN\"]}"
       req = urllib.request.Request(direct_post, data=data, headers=hdrs, method="POST")
       print(urllib.request.urlopen(req, timeout=120).read().decode())
   ' "<local_attached_file_path>" "<signed_put_url>" "<direct_post_url>" "<content_type>"
   ```
3. Use the returned `workbook_gcs_uri` (or `workbook_uri` from `direct_post_url`) as `workbook_uri` for Steps 1–2.

### Step 1: Pre-Flight Hygiene Scan, Exception Report & Go/No-Go Recommendation
1. Call `assess_workbook_onboarding_readiness(workbook_uri=..., model_slug=...)`.
2. Publish the returned `markdown_report` to `workbook_hygiene_exception_report.md` via `write_to_file` (`UserFacing=true`, `RequestFeedback=false`) so the side-pane Artifact opens immediately showing:
   - **Go / Conditional-Go / No-Go Verdict** (`GO`, `CONDITIONAL_GO`, or `NO_GO`)
   - **Readiness Metrics**: `MES` (`LES`), `MHS`, `MDR`, and `MRI`
   - **Prioritized Exception Table**: `BLOCKER`, `WARNING`, and `INFO` findings with exact `Sheet!Coord` examples and remediations
   - **Auto-Detected Targets**: Candidate scenario assumption sheets, BigQuery ML `ARIMA_PLUS` trajectory sheets, and VBA modules
3. **Human-in-the-Loop Gate 1**:
   - If `decision == "NO_GO"`, stop and explain the `BLOCKER` remediation items. Only pass `force_override=true` if the Administrator explicitly instructs to force-proceed.
   - If `decision in ("GO", "CONDITIONAL_GO")`, ask the Administrator via `ask_question` to confirm launching Stage 2 code generation & parity verification (and confirm/adjust `model_slug`).

### Step 2: Isolated Managed Agents Code Generation, Parity Loop & Repo-Free GitHub PR
1. Call `start_workbook_onboarding_job(workbook_uri=..., model_slug=..., force_override=...)`.
2. Poll `get_onboarding_job_status(job_id=...)` until `state` reaches `AWAITING_PR_APPROVAL` (or `FAILED`).
3. Present the **Parity Verification Summary** (`parity_rate_pct`, `total_compared_cells`, `pytest_passed`, `verified_locally`) alongside the clickable **GitHub Pull Request URL** (`pr_result.pr_url`).

### Step 3: Post-PR Review Deployment
1. Wait until the Administrator reviews and merges the Pull Request on GitHub.
2. Once the Administrator confirms the PR is merged and asks to deploy, call `deploy_approved_onboarding_model(model_slug=..., pr_number=..., require_merged_pr=true)`.
3. Report the provisioned BigQuery dataset (`<model_slug>_digital_twin`), `ARIMA_PLUS` status, live Cloud Run MCP URL (`<model_slug>-bq-twin-mcp`), and published Agent Registry skill IDs.
