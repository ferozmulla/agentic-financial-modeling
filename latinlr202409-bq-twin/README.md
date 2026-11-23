# `latinlr202409-bq-twin` — Latin America Refining Equilibrium BigQuery Digital Twin

Isolated BigQuery Digital Twin (`comm-model-mod.latinlr202409_digital_twin`), 4-Ws Governance Audit Ledger, BigQuery ML `ARIMA_PLUS` time-series forecasting, iterative circular equilibrium solver (`iterateCount=1`), and Streamable HTTP Remote MCP Server (`latinlr202409-bq-twin-mcp`) for `Latinlr202409.xlsx`.

## Key Highlights
- **21 Active Analytical & Crude Assay Sheets**: `Dashboard_Annual`, `Dashboard_Month`, `Yields`, `LinksOut_Annual`, `LinksOut_Month`, `UPLOAD - Annual`, `LinksIn_Annual`, `LinksIn_Monthly`, and 13 Latin American crude assays (`Escalante`, `Medanito`, `Lula`, `Marlim`, `Castilla Blend`, `Vasconia`, `Napo`, `Oriente`, `Liza`, `Unity Gold`, `Olmeca`, `Merey`, `Mesa_30`).
- **Remediation Applied**: Replaced 17,368 dynamic `INDIRECT("'Yields'!"&SUBSTITUTE(ADDRESS(...)))` column lookups across the 13 crude sheets with deterministic static `Yields` range references (`Yields!$F$18:$S$35` and `Yields!$F$60:$S$77`) and pruned 2,423 broken `#REF!` defined names.
- **Numeric Parity**: `100.00%` match across `283,896` evaluated numeric formula cells on the 19 core analytical & crude sheets (`rtol=1e-4, atol=1e-4`).
