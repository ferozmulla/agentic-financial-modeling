"""Top-level re-export shim for brazil_power_agent.mcp_server."""

from __future__ import annotations

from brazil_power_agent.mcp_server import (
    GEMINI_ENTERPRISE_APP_ID,
    MCP_PROTOCOL_VERSION,
    MCP_SERVER_NAME,
    MCP_SERVER_VERSION,
    MCP_TOOLS,
    build_mcp_server_config_entry,
    dispatch_mcp_tool,
    get_default_session_manager,
    handle_jsonrpc_request,
    main,
    register_mcp_config,
    serve_stdio_stream,
)

__all__ = [
    "GEMINI_ENTERPRISE_APP_ID",
    "MCP_PROTOCOL_VERSION",
    "MCP_SERVER_NAME",
    "MCP_SERVER_VERSION",
    "MCP_TOOLS",
    "build_mcp_server_config_entry",
    "dispatch_mcp_tool",
    "get_default_session_manager",
    "handle_jsonrpc_request",
    "main",
    "register_mcp_config",
    "serve_stdio_stream",
]
