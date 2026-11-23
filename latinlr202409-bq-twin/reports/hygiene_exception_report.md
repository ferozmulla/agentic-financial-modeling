# Workbook Onboarding Hygiene & Exception Report — `Latinlr202409_remediated.xlsx`

- **Onboarding Recommendation**: **`CONDITIONAL_GO`**
- **Target Model Slug**: `latinlr202409`
- **Detected Archetype**: `Circular Equilibrium Time-Series Model`
- **Readiness Tier**: Tier 1 — Fast-Track Automated Port
- **Scale**: `22` tabs | `377,758` populated cells | `348,926` formulas (`11.20` MB)
- **Calculation Mode**: Iterative (`iterateCount=1`)

## 1. Executive Scorecard

| Metric | Score | Interpretation |
| :--- | ---: | :--- |
| **Model Extractability Score (`MES` / `LES`)** | **94.6%** | Higher = more deterministic formula/VBA extraction |
| **Model Hygiene Score (`MHS`)** | **73.4%** | Structural cleanliness & reference integrity |
| **Model Defect Rate (`MDR = 100 - MHS`)** | **26.6%** | Lower = fewer broken cells, islands, or link issues |
| **Modernization Readiness Index (`MRI`)** | **85.1%** | Composite readiness score (`>=80%` Go, `<50%` No-Go) |

### Go / No-Go Rationale
- Passed hard extractability blockers (MES=94.6%, MRI=85.1%), with 4 warning(s) requiring reviewer verification in the Git PR.
- [WARNING:SNAPSHOT_EXTERNAL_LINKS] External Workbook Links Snapshotted from Cached Values (99.9% cached) (affected=26936).
- [WARNING:EVALUATED_CELL_ERROR] Evaluated Formula Cell Errors (#REF!, #VALUE!, #DIV/0!, #NAME?) (affected=283).
- [WARNING:BROKEN_FORMULA_REFERENCE] Broken Formula Reference (affected=115).
- [WARNING:ELEVATED_DEFECT_OR_MODERATE_MRI] Moderate Readiness / Elevated Defect Rate (MRI=85.1%, MDR=26.6%) (affected=1).

## 2. Exception Report

| Severity | Sub-Metric | Code | Affected | Sample Locations | Remediation |
| :---: | :---: | :--- | ---: | :--- | :--- |
| **WARNING** | `E4/H4` | `SNAPSHOT_EXTERNAL_LINKS` | 26,936 | `Dashboard_Annual!B52`, `Dashboard_Annual!C52`, `Dashboard_Annual!D52`, `Dashboard_Annual!E52`, `Dashboard_Annual!F52` | External [N]Sheet!Cell links will be materialized into dt_external_links using cached baseline values unless peer workbooks are supplied. |
| **WARNING** | `H1` | `EVALUATED_CELL_ERROR` | 283 | `Dashboard_Annual!B111`, `Dashboard_Annual!C111`, `LinksOut_Month!IM73`, `LinksOut_Month!IN73`, `LinksOut_Month!IO73` | Inspect flagged formula cells; fix broken references or guard intentional zero-divisors with IFERROR(). |
| **WARNING** | `H3` | `BROKEN_FORMULA_REFERENCE` | 115 | `Escalante!DA885`, `Escalante!DB885`, `Escalante!DC885`, `Escalante!DD885`, `Escalante!DE885` | Review flagged cell coordinates during PR inspection. |
| **WARNING** | `MRI/MDR` | `ELEVATED_DEFECT_OR_MODERATE_MRI` | 1 | — | Proceed with Conditional-Go; verify flagged defect coordinates against parity report in the Git PR. |
| **INFO** | `H2` | `UNLOCKED_DRAG_REFERENCE_DRIFT` | 102 | `LinksOut_Month!IM73`, `LinksOut_Month!IN73`, `LinksOut_Month!IO73`, `LinksOut_Month!IP73`, `LinksOut_Month!IQ73` | Add '$' row/column anchors to lookup table ranges in dragged formulas. |

## 3. Detected Onboarding Targets

- **Candidate Scenario Assumption Tabs**: `Dashboard_Month`, `Dashboard_Annual`, `Yields`
- **Candidate BigQuery ML `ARIMA_PLUS` Time-Series Tabs**: `LinksOut_Month`, `LinksOut_Annual`, `UPLOAD - Annual`, `Escalante`, `Medanito`, `Lula`, `Marlim`, `Castilla Blend`, `Vasconia`, `Napo`, `Oriente`, `Liza`, `Unity Gold`, `Olmeca`, `Merey`, `Mesa_30`, `LinksIn_Annual`, `LinksIn_Monthly`
- **VBA Modules (`0`)**: Macro-free workbook
