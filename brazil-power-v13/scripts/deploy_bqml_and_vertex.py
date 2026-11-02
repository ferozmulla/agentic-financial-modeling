"""Seeds BigQuery ML tables, provisions the Remote Connection, and deploys BQML + Vertex AI models."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

from google.cloud import bigquery

from src.bqml.surrogate_trainer import BQMLConnectedSheetsEngine
from src.core.config import PROJECT_ROOT, get_settings
from src.solver.workbook_context import get_baseline_solver_context

GATEWAY_URL = "https://sheets-commodity-mod-gateway-1024543888590.us-central1.run.app"
CONNECTION_ID = "sheets-mod-vertex-conn"


def _run_cmd(cmd: list[str]) -> str:
    env = os.environ.copy()
    existing_metrics = env.get("CLOUDSDK_METRICS_ENVIRONMENT", "")
    env["CLOUDSDK_METRICS_ENVIRONMENT"] = (
        f"{existing_metrics} datacloud.antigravity".strip()
    )
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
        )
    return proc.stdout.strip()


def _get_access_token() -> str:
    proc = subprocess.run(
        [
            "gcloud",
            "auth",
            "print-access-token",
            "admin@ferozmulla.altostrat.com",
            "--scopes=https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/drive",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    proc2 = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc2.returncode == 0 and proc2.stdout.strip():
        return proc2.stdout.strip()
    raise RuntimeError(f"Failed to obtain access token: {proc.stderr}")


def ensure_bq_remote_connection(project_id: str, region: str) -> str:
    """Ensure us-central1.sheets-mod-vertex-conn exists and grant roles/run.invoker on Cloud Run."""
    import urllib.error
    import urllib.request

    token = _get_access_token()
    conn_url = (
        f"https://bigqueryconnection.googleapis.com/v1/projects/{project_id}"
        f"/locations/{region}/connections/{CONNECTION_ID}"
    )
    req = urllib.request.Request(
        conn_url,
        headers={
            "Authorization": f"Bearer {token}",
            "x-goog-user-project": project_id,
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            conn_info = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError:
        create_url = (
            f"https://bigqueryconnection.googleapis.com/v1/projects/{project_id}"
            f"/locations/{region}/connections?connectionId={CONNECTION_ID}"
        )
        create_req = urllib.request.Request(
            create_url,
            data=json.dumps({"cloudResource": {}}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "x-goog-user-project": project_id,
            },
            method="POST",
        )
        with urllib.request.urlopen(create_req) as resp:
            conn_info = json.loads(resp.read().decode("utf-8"))

    sa_email = conn_info["cloudResource"]["serviceAccountId"]

    # Bind roles/run.invoker on sheets-commodity-mod-gateway via Cloud Run REST API
    iam_base = (
        f"https://run.googleapis.com/v2/projects/{project_id}/locations/{region}"
        f"/services/sheets-commodity-mod-gateway"
    )
    get_iam_req = urllib.request.Request(
        f"{iam_base}:getIamPolicy",
        headers={
            "Authorization": f"Bearer {token}",
            "x-goog-user-project": project_id,
        },
    )
    with urllib.request.urlopen(get_iam_req) as resp:
        policy = json.loads(resp.read().decode("utf-8"))

    bindings: list[dict[str, Any]] = policy.get("bindings", [])
    member_str = f"serviceAccount:{sa_email}"
    invoker_binding = next((b for b in bindings if b.get("role") == "roles/run.invoker"), None)
    if invoker_binding is None:
        bindings.append({"role": "roles/run.invoker", "members": [member_str]})
    elif member_str not in invoker_binding.get("members", []):
        invoker_binding.setdefault("members", []).append(member_str)
    policy["bindings"] = bindings

    set_iam_req = urllib.request.Request(
        f"{iam_base}:setIamPolicy",
        data=json.dumps({"policy": policy}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "x-goog-user-project": project_id,
        },
        method="POST",
    )
    with urllib.request.urlopen(set_iam_req) as resp:
        resp.read()

    return str(sa_email)


def extract_empirical_lt_rows() -> list[dict[str, Any]]:
    """Extract the 445 empirical trajectory rows from LT Capex, LT Fuel, and LT CF in the seed workbook."""
    import openpyxl

    settings = get_settings()
    seed_path = (
        settings.seed_workbook_path
        if settings.seed_workbook_path.is_absolute()
        else PROJECT_ROOT / settings.seed_workbook_path
    )
    wb = openpyxl.load_workbook(seed_path, data_only=True, read_only=True)
    lt_rows: list[dict[str, Any]] = []

    capex_fuel_cols = [
        (1, "CCGT"),
        (2, "Bio_CHP"),
        (3, "Bio_retro"),
        (4, "Bio_WC"),
        (5, "Wind"),
        (6, "Solar"),
        (7, "Coal_PC"),
        (8, "SHP"),
        (9, "Coal_CFBC"),
        (10, "GDPV_RES"),
        (11, "GDPV_COM"),
    ]
    for sheet_name, family in (("LT Capex", "LT_CAPEX"), ("LT Fuel", "LT_FUEL")):
        ws = wb[sheet_name]
        for row in ws.iter_rows(min_row=8, max_row=30, values_only=True):
            yr = row[0]
            if not isinstance(yr, (int, float)):
                continue
            yr_int = int(yr)
            for col_idx, tech_code in capex_fuel_cols:
                val = row[col_idx] if col_idx < len(row) else None
                if isinstance(val, (int, float)):
                    lt_rows.append(
                        {
                            "forecast_year_date": f"{yr_int}-01-01",
                            "curve_family": family,
                            "technology_code": tech_code,
                            "trajectory_value": float(val),
                        }
                    )

    ws_cf = wb["LT CF"]
    cf_cols = [(5, "Wind"), (6, "Solar")]
    for row in ws_cf.iter_rows(min_row=8, max_row=34, values_only=True):
        yr = row[0]
        if not isinstance(yr, (int, float)):
            continue
        yr_int = int(yr)
        for col_idx, tech_code in cf_cols:
            val = row[col_idx] if col_idx < len(row) else None
            if isinstance(val, (int, float)):
                lt_rows.append(
                    {
                        "forecast_year_date": f"{yr_int}-01-01",
                        "curve_family": "LT_CF",
                        "technology_code": tech_code,
                        "trajectory_value": float(val),
                    }
                )

    wb.close()
    return lt_rows


def seed_bqml_tables(client: bigquery.Client, project_id: str, dataset_id: str) -> dict[str, int]:
    """Seed historical_lt_trajectories (445 empirical rows) and solver_training_grid (324 rows)."""
    ctx = get_baseline_solver_context()
    engine = BQMLConnectedSheetsEngine(ctx)

    # 1. Extract 445 empirical rows across LT_CAPEX, LT_FUEL, and LT_CF from the seed workbook
    lt_rows = extract_empirical_lt_rows()

    # 2. Build 324 training rows across all 12 technologies for solver_training_grid
    training_rows: list[dict[str, Any]] = []
    tech_codes = [f"_{i:02d}_CF" for i in range(1, 13)]
    for tech in tech_codes:
        for capex_mult in (0.85, 1.0, 1.15):
            for fuel_mult in (0.85, 1.0, 1.15):
                for cf_mult in (0.90, 1.0, 1.10):
                    for wacc, life in ((0.07, 25), (0.08, 25), (0.095, 20)):
                        pred = engine.predict_surrogate_lcoe(
                            technology_code=tech,
                            capex_multiplier=capex_mult,
                            fuel_cost_multiplier=fuel_mult,
                            capacity_factor_multiplier=cf_mult,
                            wacc_rate=wacc,
                            economic_life_yrs=life,
                        )
                        training_rows.append(
                            {
                                "technology_code": tech,
                                "capex_multiplier": capex_mult,
                                "fuel_cost_multiplier": fuel_mult,
                                "capacity_factor_multiplier": cf_mult,
                                "wacc_rate": wacc,
                                "economic_life_yrs": life,
                                "solved_lcoe": float(pred["predicted_lcoe"]),
                            }
                        )

    lt_table_ref = f"{project_id}.{dataset_id}.historical_lt_trajectories"
    grid_table_ref = f"{project_id}.{dataset_id}.solver_training_grid"

    load_cfg = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        labels={"datacloud": "antigravity"},
    )
    client.load_table_from_json(lt_rows, lt_table_ref, job_config=load_cfg).result()
    client.load_table_from_json(training_rows, grid_table_ref, job_config=load_cfg).result()

    return {
        "historical_lt_trajectories_rows": len(lt_rows),
        "solver_training_grid_rows": len(training_rows),
    }


def deploy_bqml_sql(client: bigquery.Client, project_id: str) -> list[str]:
    """Execute 003_bqml_forecasts_remote_fn_and_surrogate.sql statements in BigQuery."""
    sql_path = PROJECT_ROOT / "sql" / "bigquery" / "003_bqml_forecasts_remote_fn_and_surrogate.sql"
    raw_sql = sql_path.read_text(encoding="utf-8")
    rendered_sql = raw_sql.replace("${CLOUD_RUN_GATEWAY_URL}", GATEWAY_URL)

    statements = [stmt.strip() for stmt in rendered_sql.split(";") if stmt.strip()]
    executed: list[str] = []
    q_cfg = bigquery.QueryJobConfig(
        default_dataset=f"{project_id}.sheets_commodity_mod_governance",
        labels={"datacloud": "antigravity"},
    )
    for idx, stmt in enumerate(statements, start=1):
        first_line = next(
            (line.strip() for line in stmt.splitlines() if not line.strip().startswith("--")),
            f"Statement #{idx}",
        )
        print(f"Executing BQML DDL [{idx}/{len(statements)}]: {first_line} ...", flush=True)
        client.query(stmt, job_config=q_cfg).result()
        executed.append(first_line)
    return executed


def verify_live_bqml(client: bigquery.Client, project_id: str, dataset_id: str) -> dict[str, Any]:
    """Run live verification queries against the forecast view, Remote Function, and Surrogate Model view."""
    q_cfg = bigquery.QueryJobConfig(labels={"datacloud": "antigravity"})

    # 1. Verify pivoted vw_connected_sheets_lt_forecasts (backing LT_Capex_BQML, LT_Fuel_BQML, LT_CF_BQML)
    forecast_rows = list(
        client.query(
            f"""
            SELECT curve_sheet, Yr, Data_Source, CCGT, Wind, Solar
            FROM `{project_id}.{dataset_id}.vw_connected_sheets_lt_forecasts`
            WHERE Yr IN (2025, 2026)
            ORDER BY curve_sheet, Yr
            """,
            job_config=q_cfg,
        ).result()
    )

    # 2. Verify BigQuery Remote Function fn_solve_lcoe -> Cloud Run /v1/bqml/solve
    remote_fn_rows = list(
        client.query(
            f"""
            SELECT `{project_id}.{dataset_id}.fn_solve_lcoe`('calcule_tir1', JSON '{{}}') AS solver_result
            """,
            job_config=q_cfg,
        ).result()
    )

    # 3. Verify Connected Sheets Surrogate View vw_bqml_lcoe_surrogate_predictions
    surrogate_rows = list(
        client.query(
            f"""
            SELECT
              technology_code,
              exact_solver_lcoe,
              bqml_predicted_lcoe,
              residual_diff
            FROM `{project_id}.{dataset_id}.vw_bqml_lcoe_surrogate_predictions`
            WHERE technology_code = '_01_CF'
              AND capex_multiplier = 1.0
              AND fuel_cost_multiplier = 1.0
              AND capacity_factor_multiplier = 1.0
              AND wacc_rate = 0.08
            LIMIT 3
            """,
            job_config=q_cfg,
        ).result()
    )

    return {
        "forecast_sample": [dict(r) for r in forecast_rows],
        "remote_function_sample": str(remote_fn_rows[0]["solver_result"])[:300]
        if remote_fn_rows
        else None,
        "surrogate_prediction_sample": [dict(r) for r in surrogate_rows],
    }


def _get_bq_client(project_id: str, location: str) -> bigquery.Client:
    from google.oauth2.credentials import Credentials as OAuthCredentials

    token = _get_access_token()
    creds = OAuthCredentials(
        token=token,
        quota_project_id=project_id,
    )
    return bigquery.Client(project=project_id, location=location, credentials=creds)


def main() -> int:
    settings = get_settings()
    client = _get_bq_client(settings.gcp_project_id, settings.bq_location)

    print("1. Ensuring BigQuery Remote Connection & Cloud Run IAM binding...", flush=True)
    conn_sa = ensure_bq_remote_connection(settings.gcp_project_id, settings.gcp_region)

    print("2. Seeding historical_lt_trajectories and solver_training_grid...", flush=True)
    seed_counts = seed_bqml_tables(client, settings.gcp_project_id, settings.bq_dataset_id)

    print("3. Executing 003_bqml_forecasts_remote_fn_and_surrogate.sql in BigQuery...", flush=True)
    ddl_executed = deploy_bqml_sql(client, settings.gcp_project_id)

    print("4. Verifying live BQML ARIMA_PLUS forecast, Remote Function, and Surrogate Model...", flush=True)
    verification = verify_live_bqml(client, settings.gcp_project_id, settings.bq_dataset_id)

    summary = {
        "project_id": settings.gcp_project_id,
        "dataset_id": settings.bq_dataset_id,
        "remote_connection_service_account": conn_sa,
        "seed_counts": seed_counts,
        "ddl_executed": ddl_executed,
        "verification": verification,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
