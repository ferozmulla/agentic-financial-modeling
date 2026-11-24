# Latinlr202409 BigQuery Digital Twin

Autonomous workbook-free twin for the `latinlr202409` crude equilibrium and forecasting model.

## Features
- Fast XML workbook compiler for seed ingestion
- Pure SQL BigQuery state persistence & scenario delta overlays
- Deterministic Circular/DAG Python solver matching workbook formula outcomes
- Production-grade FastAPI SSE & HTTP MCP Server supporting 7 core tools
- Multi-skill Analyst Suite including 1 orchestrator and 4 shortcut skills

## Installation & Local Running
```bash
pip install -e .
uvicorn latinlr202409_bq_twin.mcp_app:app --reload --port 8080
```
