"""JSON-RPC 2.0 MCP Tool Schemas and Dispatcher for `model-onboarding-mcp`."""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

from model_onboarding.config import OnboardingSettings, get_onboarding_settings
from model_onboarding.controller import OnboardingController
from model_onboarding.hygiene_gate import render_hygiene_exception_markdown

logger = logging.getLogger(__name__)

MCP_SERVER_NAME = "model-onboarding-mcp"
MCP_SERVER_VERSION = "1.1.0"

ONBOARDING_MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "create_workbook_upload_url",
        "description": (
            "Mint a short-lived GCS V4 Signed PUT URL and direct POST /v1/uploads fallback so a Cowork "
            "session can stream a `+`-attached local .xlsx or .xlsm file directly into cloud staging "
            "without manual gsutil steps or passing binary bytes through LLM tokens."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Original workbook filename ending in .xlsx or .xlsm (e.g. 'NewModel.xlsm').",
                }
            },
            "required": ["filename"],
        },
    },
    {
        "name": "assess_workbook_onboarding_readiness",
        "description": (
            "Run Stage 1 deterministic MES/MDR hygiene scan on an Energy modeling spreadsheet "
            "(gs:// URI or staged server path), returning the Exception Report and GO / CONDITIONAL_GO / NO_GO recommendation."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "workbook_uri": {
                    "type": "string",
                    "description": "Cloud Storage URI (gs://bucket/uploads/.../file.xlsm) or staged server path.",
                },
                "model_slug": {
                    "type": "string",
                    "description": "Optional lowercase kebab-case slug (e.g. 'argentina-power-v3').",
                },
            },
            "required": ["workbook_uri"],
        },
    },
    {
        "name": "start_workbook_onboarding_job",
        "description": (
            "Launch Stage 2 Managed Agent sandbox code generation + pytest parity verification "
            "and Stage 3a Git Pull Request creation asynchronously (or synchronously when run_sync=true)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "workbook_uri": {
                    "type": "string",
                    "description": "Cloud Storage URI (gs://bucket/file.xlsm) or staged server path.",
                },
                "model_slug": {
                    "type": "string",
                    "description": "Optional lowercase kebab-case slug.",
                },
                "force_override": {
                    "type": "boolean",
                    "description": "Set true only when an Administrator explicitly overrides a NO_GO verdict.",
                },
                "local_branch_only": {
                    "type": "boolean",
                    "description": "Commit to a local branch without pushing to GitHub.",
                },
                "run_sync": {
                    "type": "boolean",
                    "description": "Wait for job completion before returning (useful in tests and short runs).",
                },
            },
            "required": ["workbook_uri"],
        },
    },
    {
        "name": "get_onboarding_job_status",
        "description": "Retrieve current state, Hygiene Exception Report, Parity Scorecard, and Git PR link for job_id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Onboarding job ID returned by start_workbook_onboarding_job."}
            },
            "required": ["job_id"],
        },
    },
    {
        "name": "deploy_approved_onboarding_model",
        "description": (
            "Stage 3b (Post-PR Review): Pull merged <model_slug>-bq-twin from GitHub main, seed the BigQuery "
            "Digital Twin + 4-Ws audit tables, train ARIMA_PLUS BQML models, deploy the dedicated Cloud Run "
            "MCP service, and publish skills to Agent Registry."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_slug": {"type": "string", "description": "Approved model slug."},
                "pr_number": {"type": "integer", "description": "Merged GitHub Pull Request number."},
                "require_merged_pr": {
                    "type": "boolean",
                    "description": "Verify via GitHub API that pr_number is merged before deploying (default true).",
                },
                "skip_bqml": {"type": "boolean", "description": "Skip ARIMA_PLUS BQML training if true."},
            },
            "required": ["model_slug"],
        },
    },
]


class OnboardingMcpDispatcher:
    """JSON-RPC 2.0 handler wrapping `OnboardingController` with safe error sanitization."""

    def __init__(
        self,
        controller: OnboardingController | None = None,
        settings: OnboardingSettings | None = None,
    ) -> None:
        self.settings = settings or get_onboarding_settings()
        self.controller = controller or OnboardingController(settings=self.settings)

    def _dispatch_tool(self, name: str, args: dict[str, Any], base_url: str = "") -> dict[str, Any]:
        if name == "create_workbook_upload_url":
            info = self.controller.create_upload_session(
                filename=str(args["filename"]),
                base_url=base_url,
            )
            return info.model_dump(mode="json")

        if name == "assess_workbook_onboarding_readiness":
            report = self.controller.assess_only(
                source_path_or_gcs_uri=str(args["workbook_uri"]),
                model_slug=args.get("model_slug"),
            )
            return {
                "hygiene_report": report.model_dump(mode="json"),
                "markdown_report": render_hygiene_exception_markdown(report),
            }

        if name == "start_workbook_onboarding_job":
            pending = self.controller.create_pending_job(
                source_path_or_gcs_uri=str(args["workbook_uri"]),
                model_slug=args.get("model_slug"),
            )
            force = bool(args.get("force_override", False))
            local_only = bool(args.get("local_branch_only", False))
            run_sync = bool(args.get("run_sync", False))

            if run_sync:
                completed = self.controller.execute_job(
                    job_id=pending.job_id,
                    force_override=force,
                    local_branch_only=local_only,
                )
                return completed.model_dump(mode="json")

            worker_thread = threading.Thread(
                target=self.controller.execute_job,
                kwargs={
                    "job_id": pending.job_id,
                    "force_override": force,
                    "local_branch_only": local_only,
                },
                daemon=True,
            )
            worker_thread.start()
            return pending.model_dump(mode="json")

        if name == "get_onboarding_job_status":
            st = self.controller.get_job_status(str(args["job_id"]))
            return st.model_dump(mode="json")

        if name == "deploy_approved_onboarding_model":
            pr_num = args.get("pr_number")
            req_merged = bool(args.get("require_merged_pr", pr_num is not None))
            summary = self.controller.deploy_approved(
                model_slug=str(args["model_slug"]),
                skip_bqml=bool(args.get("skip_bqml", False)),
                pr_number=int(pr_num) if pr_num is not None else None,
                require_merged_pr=req_merged,
            )
            return summary.model_dump(mode="json")

        raise ValueError(f"Unknown MCP tool: {name!r}")

    def handle_jsonrpc(
        self,
        payload: dict[str, Any],
        session_id: str = "",
        base_url: str = "",
    ) -> dict[str, Any] | None:
        """Process a single MCP JSON-RPC 2.0 request envelope."""
        del session_id
        req_id = payload.get("id")
        method = str(payload.get("method") or "")

        if method == "notifications/initialized" or req_id is None:
            return None

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": MCP_SERVER_NAME, "version": MCP_SERVER_VERSION},
                },
            }

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": ONBOARDING_MCP_TOOLS},
            }

        if method == "tools/call":
            params = payload.get("params") or {}
            tool_name = str(params.get("name") or "")
            tool_args = params.get("arguments") or {}
            try:
                structured = self._dispatch_tool(tool_name, tool_args, base_url=base_url)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(structured, indent=2)}],
                        "structuredContent": structured,
                        "isError": False,
                    },
                }
            except (ValueError, FileNotFoundError) as exc:
                logger.warning("Onboarding tool validation error in %s: %s", tool_name, type(exc).__name__)
                err_msg = str(exc)[:300]
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps({"error": err_msg})}],
                        "isError": True,
                    },
                }
            except Exception:
                logger.exception("Unhandled server error executing onboarding tool %s", tool_name)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps({"error": "Internal onboarding execution error."}),
                            }
                        ],
                        "isError": True,
                    },
                }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": "Method not found"},
        }
