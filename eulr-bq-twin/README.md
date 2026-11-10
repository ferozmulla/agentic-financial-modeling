# EULR European Refining Equilibrium — All-in-BigQuery Digital Twin (`eulr-bq-twin`)

100% Excel-free, strictly segregated Agentic Digital Twin and Cloud Run Remote MCP Server for the European Long-Range Crude & Refined Products Equilibrium Model (`Eulr202409.xlsx`).

- **GCP Project**: `comm-model-mod` (`us-central1`)
- **BigQuery Dataset**: `comm-model-mod.eulr_digital_twin`
- **Cloud Storage Vault**: `gs://comm-model-mod-eulr-twin-vault`
- **Cloud Run Remote MCP**: `eulr-bq-twin-mcp` (`https://eulr-bq-twin-mcp-2wcxwkmdga-uc.a.run.app` — `/mcp/sse`, `/mcp`, `/v1/exports/{filename}`, `/healthz`)
- **Service Account**: `sa-eulr-bq-twin@comm-model-mod.iam.gserviceaccount.com`
- **Gemini Agent Skills**: `eulr-refining-model-gcp`, `eulr-equilibrium-gcp`, `eulr-scenario-matrix-gcp`, `eulr-bqml-gcp`, `eulr-hck-economics-gcp`
