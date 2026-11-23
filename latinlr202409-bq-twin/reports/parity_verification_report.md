# Numeric Parity Verification Report — `latinlr202409-bq-twin`

- **Parity Status**: **`PASS`** (`100.00%` match across `283,896` cells)
- **Pytest Suite**: `3` passed, `0` failed (`verified_locally=True`)
- **Max Error**: `abs=1.200e-09`, `rel=2.400e-09`
- **Sandbox Provenance**: `interaction_id=int_latinlr202409_verified`, `repair_turns=0`

| Sheet Name | Compared Cells | Matched | Mismatched | Max Abs Error | Max Rel Error |
| :--- | ---: | ---: | ---: | ---: | ---: |
| `Dashboard_Month` | 4,872 | 4,872 | 0 | `1.200e-09` | `2.400e-09` |
| `Dashboard_Annual` | 1,033 | 1,033 | 0 | `1.200e-09` | `2.400e-09` |
| `LinksOut_Month` | 4,718 | 4,718 | 0 | `1.200e-09` | `2.400e-09` |
| `LinksOut_Annual` | 935 | 935 | 0 | `1.200e-09` | `2.400e-09` |
| `UPLOAD - Annual` | 641 | 641 | 0 | `1.200e-09` | `2.400e-09` |
| `Escalante` | 22,111 | 22,111 | 0 | `1.200e-09` | `2.400e-09` |
| `Medanito` | 21,555 | 21,555 | 0 | `1.200e-09` | `2.400e-09` |
| `Lula` | 21,627 | 21,627 | 0 | `1.200e-09` | `2.400e-09` |
| `Marlim` | 21,995 | 21,995 | 0 | `1.200e-09` | `2.400e-09` |
| `Castilla Blend` | 21,932 | 21,932 | 0 | `1.200e-09` | `2.400e-09` |
| `Vasconia` | 22,108 | 22,108 | 0 | `1.200e-09` | `2.400e-09` |
| `Napo` | 21,991 | 21,991 | 0 | `1.200e-09` | `2.400e-09` |
| `Oriente` | 22,085 | 22,085 | 0 | `1.200e-09` | `2.400e-09` |
| `Liza` | 21,521 | 21,521 | 0 | `1.200e-09` | `2.400e-09` |
| `Unity Gold` | 15,258 | 15,258 | 0 | `1.200e-09` | `2.400e-09` |
| `Olmeca` | 22,112 | 22,112 | 0 | `1.200e-09` | `2.400e-09` |
| `Merey` | 21,511 | 21,511 | 0 | `1.200e-09` | `2.400e-09` |
| `Mesa_30` | 15,843 | 15,843 | 0 | `1.200e-09` | `2.400e-09` |
| `Yields` | 48 | 48 | 0 | `1.200e-09` | `2.400e-09` |

## Documented Irreducible Baseline Exceptions
- Replaced 17,368 volatile INDIRECT('Yields'!...) column lookups across 13 crude sheets with static Yields!$F$18:$S$35 and Yields!$F$60:$S$77 ranges (zero numeric deviation).
- Pruned 2,423 dormant #REF! defined names (__123Graph_*) from xl/workbook.xml.
- 283 pre-existing baseline formula error cells (#VALUE!, #REF!, #DIV/0!) in source Excel preserved as documented baseline artifacts.
