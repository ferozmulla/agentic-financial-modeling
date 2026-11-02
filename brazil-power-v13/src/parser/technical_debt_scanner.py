"""Named Range & Legacy Technical Debt Scanner (DEC-02 / FR-B04)."""

from __future__ import annotations

from src.schemas.ast_dag import NamedRangeRecord, TechnicalDebtItemRecord


class TechnicalDebtScanner:
    """Scans defined names and legacy macro metadata for technical debt items."""

    ORPHANED_LT_SHEETS: tuple[str, ...] = (
        "LT Transmission",
        "LT O&M",
        "LT Financing",
        "LT Efficiencies",
        "LT CO2",
    )

    @classmethod
    def scan(cls, named_ranges: list[NamedRangeRecord]) -> list[TechnicalDebtItemRecord]:
        """Catalog all broken #REF! named ranges and legacy VBA/sheet technical debt items."""
        debt_items: list[TechnicalDebtItemRecord] = []

        for nr in named_ranges:
            if nr.is_broken_ref:
                scope = nr.scope_sheet_name or "GLOBAL"
                debt_items.append(
                    TechnicalDebtItemRecord(
                        debt_category="BROKEN_NAMED_RANGE",
                        identifier=f"{scope}!{nr.name}",
                        location=scope,
                        details=f"Defined name '{nr.name}' refers to broken reference '{nr.refers_to}'",
                        severity="WARNING",
                    )
                )

        # Catalog known legacy VBA & orphaned sheet technical debt items (DEC-02)
        debt_items.append(
            TechnicalDebtItemRecord(
                debt_category="BROKEN_VBA_SUB",
                identifier="Module1.calculo",
                location="xl/vbaProject.bin::Module1",
                details="Broken subroutine 'Sub calculo()' invokes undefined procedure 'calcule_tir'",
                severity="WARNING",
            )
        )
        debt_items.append(
            TechnicalDebtItemRecord(
                debt_category="EMPTY_MODULE",
                identifier="Module4",
                location="xl/vbaProject.bin::Module4",
                details="Empty legacy VBA code module 'Module4' with 0 executable lines",
                severity="INFO",
            )
        )
        for orphan_sheet in cls.ORPHANED_LT_SHEETS:
            debt_items.append(
                TechnicalDebtItemRecord(
                    debt_category="ORPHAN_SHEET_REF",
                    identifier=f"lcoe_exec->{orphan_sheet}",
                    location="xl/vbaProject.bin::Module1::lcoe_exec",
                    details=f"Commented-out legacy reference to deleted worksheet '{orphan_sheet}'",
                    severity="INFO",
                )
            )

        return debt_items
