# Portfolio Assessment — Workbook Modernization Scoring (`LES`, `MHS`, `MRI`)

Read-only OpenXML + MS-OVBA scanner evaluating candidate spreadsheets across:
- **Logic Extractability Score (`LES`, 0–100%)**
- **Model Hygiene Score (`MHS`, 0–100%)** + **Defect Rate (`100% - MHS`)**
- **Modernization Readiness Index (`MRI`, 0–100%)**

## Quickstart

```bash
# Run lint + unit/E2E tests
make -C portfolio-assessment lint
make -C portfolio-assessment test

# Scan workspace models (offline link hygiene mode)
PYTHONPATH=portfolio-assessment/src .venv/bin/python -m portfolio_assessment.cli

# Scan on S&P Corporate Laptop with live SharePoint/OneDrive reference verification
PYTHONPATH=portfolio-assessment/src .venv/bin/python -m portfolio_assessment.cli \
  --scan-dirs "brazil-power-v13/seed" "Eulr" "other models" \
  --reference-roots "Eulr/docs/references" "$HOME/OneDrive - S&P Global"
```
