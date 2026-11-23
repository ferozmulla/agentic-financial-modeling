"""Hardened FastAPI Remote MCP Server (`model-onboarding-mcp`) with Streamable HTTP, SSE & Binary Upload."""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import time
import uuid
from collections import deque
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from model_onboarding.mcp_tools import MCP_SERVER_NAME, MCP_SERVER_VERSION, OnboardingMcpDispatcher

_ALLOWED_METHODS = {"GET", "POST"}

_SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def _verify_optional_bearer_token(request: Request) -> bool:
    """
    Validate `ONBOARD_API_BEARER_TOKEN` when configured.
    # TODO(security): Enforce Cloud Run IAM OIDC authentication (`--no-allow-unauthenticated`) in production deployments.
    """
    expected = os.getenv("ONBOARD_API_BEARER_TOKEN", "").strip()
    if not expected:
        return True
    auth_hdr = request.headers.get("Authorization", "")
    if not auth_hdr.startswith("Bearer "):
        return False
    presented = auth_hdr[7:].strip()
    return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))


def create_onboarding_mcp_app(
    dispatcher: OnboardingMcpDispatcher | None = None,
    rate_limit_per_minute: int = 120,
    upload_to_gcs: bool | None = None,
) -> FastAPI:
    """Create FastAPI app supporting Streamable HTTP (`/mcp`), Cowork SSE (`/mcp/sse`), and `/v1/uploads`."""
    app = FastAPI(
        title="Energy Model Onboarding — Remote MCP Server",
        version=MCP_SERVER_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    mcp_dispatcher = dispatcher or OnboardingMcpDispatcher()
    sse_queues: dict[str, asyncio.Queue[str]] = {}
    request_buckets: dict[str, deque[float]] = {}

    @app.middleware("http")
    async def security_and_rate_limit_middleware(request: Request, call_next: Any) -> Response:
        if request.method.upper() not in _ALLOWED_METHODS:
            return JSONResponse(
                status_code=405,
                content={"error": "Method not allowed"},
                headers=_SECURITY_HEADERS,
            )

        client_host = request.client.host if request.client else "127.0.0.1"
        now = time.monotonic()
        bucket = request_buckets.setdefault(client_host, deque())
        while bucket and (now - bucket[0]) > 60.0:
            bucket.popleft()
        if len(bucket) >= rate_limit_per_minute:
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded"},
                headers=_SECURITY_HEADERS,
            )
        bucket.append(now)

        if request.url.path not in {"/health", "/healthz"} and not _verify_optional_bearer_token(request):
            return JSONResponse(
                status_code=401,
                content={"error": "Unauthorized"},
                headers=_SECURITY_HEADERS,
            )

        response: Response = await call_next(request)
        for hdr_k, hdr_v in _SECURITY_HEADERS.items():
            response.headers.setdefault(hdr_k, hdr_v)
        return response

    @app.get("/health")
    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": MCP_SERVER_NAME,
            "version": MCP_SERVER_VERSION,
            "gcp_project": mcp_dispatcher.settings.gcp_project_id,
            "staging_bucket": mcp_dispatcher.settings.staging_bucket,
        }

    @app.post("/mcp")
    async def mcp_streamable_http(request: Request) -> Response:
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid JSON request body"},
                headers=_SECURITY_HEADERS,
            )
        if not isinstance(body, dict):
            return JSONResponse(
                status_code=400,
                content={"error": "JSON-RPC payload must be an object"},
                headers=_SECURITY_HEADERS,
            )

        sess_hdr = request.headers.get("Mcp-Session-Id") or mcp_dispatcher.settings.default_session_id
        base_url = str(request.base_url).rstrip("/")
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(
            None,
            mcp_dispatcher.handle_jsonrpc,
            body,
            sess_hdr,
            base_url,
        )
        if resp is None:
            return Response(status_code=202, headers=_SECURITY_HEADERS)
        return JSONResponse(content=resp, headers=_SECURITY_HEADERS)

    @app.get("/mcp/sse")
    async def mcp_sse_connect(request: Request) -> StreamingResponse:
        session_id = str(uuid.uuid4())
        q: asyncio.Queue[str] = asyncio.Queue()
        sse_queues[session_id] = q
        msg_endpoint = f"/mcp/messages?session_id={session_id}"

        async def event_stream() -> Any:
            try:
                yield f"event: endpoint\ndata: {msg_endpoint}\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        payload_str = await asyncio.wait_for(q.get(), timeout=15.0)
                        yield f"event: message\ndata: {payload_str}\n\n"
                    except TimeoutError:
                        yield ": keepalive\n\n"
            finally:
                sse_queues.pop(session_id, None)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                **_SECURITY_HEADERS,
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/mcp/messages")
    async def mcp_sse_message(request: Request, session_id: str) -> Response:
        q = sse_queues.get(session_id)
        if q is None:
            raise HTTPException(status_code=404, detail="Unknown or expired MCP SSE session")
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

        base_url = str(request.base_url).rstrip("/")
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(
            None,
            mcp_dispatcher.handle_jsonrpc,
            body,
            session_id,
            base_url,
        )
        if resp is not None:
            await q.put(json.dumps(resp))
        return Response(status_code=202, headers=_SECURITY_HEADERS)

    @app.post("/v1/uploads/{upload_id}/{filename}")
    async def upload_workbook_binary(upload_id: str, filename: str, request: Request) -> JSONResponse:
        """Accept raw `.xlsx`/`.xlsm` bytes from Cowork `+` session uploads and stage to GCS."""
        raw_bytes = await request.body()
        if not raw_bytes:
            return JSONResponse(
                status_code=400,
                content={"error": "Empty upload body"},
                headers=_SECURITY_HEADERS,
            )

        use_gcs = (
            upload_to_gcs
            if upload_to_gcs is not None
            else (mcp_dispatcher.settings.gcp_project_id != "offline-test")
        )
        try:
            loop = asyncio.get_running_loop()
            staged_uri = await loop.run_in_executor(
                None,
                mcp_dispatcher.controller.store_uploaded_workbook_bytes,
                upload_id,
                filename,
                raw_bytes,
                use_gcs,
            )
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"error": str(exc)[:300]},
                headers=_SECURITY_HEADERS,
            )
        except (OSError, RuntimeError):
            return JSONResponse(
                status_code=500,
                content={"error": "Workbook upload staging failed"},
                headers=_SECURITY_HEADERS,
            )

        return JSONResponse(
            status_code=201,
            content={"upload_id": upload_id, "workbook_uri": staged_uri},
            headers=_SECURITY_HEADERS,
        )

    return app


app = create_onboarding_mcp_app()
