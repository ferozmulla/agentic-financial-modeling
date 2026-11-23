"""Streamable HTTP FastAPI Remote MCP Server (`latinlr202409-bq-twin-mcp`)."""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from .mcp_tools import (
    MCP_PROTOCOL_VERSION,
    MCP_SERVER_NAME,
    MCP_SERVER_VERSION,
    TWIN_MCP_TOOLS,
    TwinMcpDispatcher,
)


def create_mcp_app(dispatcher: TwinMcpDispatcher | None = None) -> FastAPI:
    app = FastAPI(title=MCP_SERVER_NAME, version=MCP_SERVER_VERSION)
    disp = dispatcher or TwinMcpDispatcher()

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        resp: Response = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return resp

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "service": MCP_SERVER_NAME, "version": MCP_SERVER_VERSION}

    @app.post("/mcp")
    async def handle_mcp(request: Request) -> JSONResponse:
        body: dict[str, Any] = await request.json()
        rpc_id = body.get("id", 1)
        method = str(body.get("method") or "")
        params = body.get("params") or {}

        if method == "initialize":
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "result": {
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "serverInfo": {"name": MCP_SERVER_NAME, "version": MCP_SERVER_VERSION},
                        "capabilities": {"tools": {"listChanged": False}},
                    },
                }
            )
        if method == "tools/list":
            return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "result": {"tools": TWIN_MCP_TOOLS}})
        if method == "tools/call":
            tname = str(params.get("name") or "")
            targs = params.get("arguments") or {}
            try:
                res = disp.call_tool(tname, targs)
                return JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": rpc_id,
                        "result": {
                            "content": [{"type": "text", "text": json.dumps(res, indent=2)}],
                            "structuredContent": res,
                            "isError": False,
                        },
                    }
                )
            except Exception as exc:
                return JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": rpc_id,
                        "result": {
                            "content": [{"type": "text", "text": str(exc)}],
                            "isError": True,
                        },
                    }
                )
        return JSONResponse(
            {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32601, "message": f"Method not found: {method}"}},
            status_code=400,
        )

    return app


app = create_mcp_app()
