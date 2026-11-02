"""High-speed bulk persistence and query repositories for AlloyDB / PostgreSQL (< 5.0s SLA)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    AuditEventModel,
    CellDependencyEdgeModel,
    CellModel,
    MacroBindingModel,
    NamedRangeModel,
    SolverRunTelemetryModel,
    TechnicalDebtItemModel,
    WorkbookModel,
    WorkbookVersionModel,
    WorksheetModel,
)
from src.schemas.ast_dag import (
    CellSemanticRole,
    DependencyEdgeRecord,
    ExtractedCellRecord,
    ExtractedSheetRecord,
    ExtractedWorkbookGraph,
    NamedRangeRecord,
)
from src.schemas.audit import AuditEventRecord


class GovernanceRepository:
    """Repository for reading and bulk-inserting AST, DAG, Version, and 4-Ws Audit records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_workbook_by_spreadsheet_id(self, spreadsheet_id: str) -> WorkbookModel | None:
        stmt = select(WorkbookModel).where(WorkbookModel.spreadsheet_id == spreadsheet_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_latest_version(self, spreadsheet_id: str) -> WorkbookVersionModel | None:
        stmt = (
            select(WorkbookVersionModel)
            .where(WorkbookVersionModel.spreadsheet_id == spreadsheet_id)
            .order_by(WorkbookVersionModel.version_seq_num.desc())
            .limit(1)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def load_workbook_graph(self, version_id: str) -> ExtractedWorkbookGraph | None:
        """Reconstruct ExtractedWorkbookGraph from stored AlloyDB rows for diffing."""
        v_stmt = select(WorkbookVersionModel).where(WorkbookVersionModel.version_id == version_id)
        v_row = (await self.session.execute(v_stmt)).scalar_one_or_none()
        if v_row is None:
            return None

        wb_stmt = select(WorkbookModel).where(WorkbookModel.workbook_id == v_row.workbook_id)
        wb_row = (await self.session.execute(wb_stmt)).scalar_one()

        s_rows = (
            await self.session.execute(
                select(WorksheetModel)
                .where(WorksheetModel.version_id == version_id)
                .order_by(WorksheetModel.sheet_index)
            )
        ).scalars().all()

        c_rows = (
            await self.session.execute(
                select(CellModel).where(CellModel.version_id == version_id)
            )
        ).scalars().all()

        nr_rows = (
            await self.session.execute(
                select(NamedRangeModel).where(NamedRangeModel.version_id == version_id)
            )
        ).scalars().all()

        sheets = [
            ExtractedSheetRecord(
                sheet_index=s.sheet_index,
                sheet_name=s.sheet_name,
                visibility=s.visibility,
                populated_cell_count=s.populated_cell_count,
                formula_cell_count=s.formula_cell_count,
                shared_formula_count=s.shared_formula_count,
            )
            for s in s_rows
        ]
        cells = [
            ExtractedCellRecord(
                sheet_name=c.sheet_name,
                cell_coord=c.cell_coord,
                row_num=c.row_num,
                col_num=c.col_num,
                col_letter=c.col_letter,
                data_type=c.data_type,
                raw_value=c.raw_value,
                numeric_value=c.numeric_value,
                raw_formula=c.raw_formula,
                canonical_formula=c.canonical_formula,
                r1c1_formula=c.r1c1_formula,
                formula_hash=c.formula_hash,
                shared_group_index=c.shared_group_index,
                is_shared_master=c.is_shared_master,
                semantic_role=CellSemanticRole(c.semantic_role),
            )
            for c in c_rows
        ]
        named_ranges = [
            NamedRangeRecord(
                name=nr.name,
                local_sheet_id=nr.local_sheet_id,
                scope_sheet_name=nr.scope_sheet_name,
                refers_to=nr.refers_to,
                is_broken_ref=nr.is_broken_ref,
                hidden=nr.hidden,
            )
            for nr in nr_rows
        ]

        return ExtractedWorkbookGraph(
            workbook_name=wb_row.workbook_name,
            spreadsheet_id=v_row.spreadsheet_id,
            sha256_hash=v_row.sha256_hash,
            sheets=sheets,
            cells=cells,
            dag_edges=[],
            named_ranges=named_ranges,
            macro_bindings=[],
            technical_debt_items=[],
        )

    async def get_cell_in_latest_version(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        cell_coord: str,
    ) -> tuple[WorkbookVersionModel | None, CellModel | None]:
        """Look up a single cell's baseline role and formula in the latest governed version."""
        latest_v = await self.get_latest_version(spreadsheet_id)
        if latest_v is None:
            return None, None
        stmt = select(CellModel).where(
            CellModel.version_id == latest_v.version_id,
            CellModel.sheet_name == sheet_name,
            CellModel.cell_coord == cell_coord,
        )
        cell = (await self.session.execute(stmt)).scalar_one_or_none()
        return latest_v, cell

    async def bulk_persist_version_graph(
        self,
        graph: ExtractedWorkbookGraph,
        version_id: str,
        parent_version_id: str | None,
        version_seq_num: int,
        gcs_snapshot_uri: str,
        who_google_user: str,
        who_iam_principal: str,
        commit_comment: str,
        audit_events: list[AuditEventRecord],
        structural_mutation_count: int,
        manual_override_count: int,
    ) -> None:
        """Bulk-insert workbook version, 22 sheets, 35,655 cells, DAG edges, named ranges, debt, and 4-Ws."""
        wb = await self.get_workbook_by_spreadsheet_id(graph.spreadsheet_id)
        if wb is None:
            wb = WorkbookModel(
                workbook_id=graph.spreadsheet_id,
                spreadsheet_id=graph.spreadsheet_id,
                workbook_name=graph.workbook_name,
                latest_version_id=version_id,
                latest_version_seq_num=version_seq_num,
            )
            self.session.add(wb)
            await self.session.flush()
        else:
            wb.latest_version_id = version_id
            wb.latest_version_seq_num = version_seq_num

        total_formulas = sum(s.formula_cell_count for s in graph.sheets)
        v_model = WorkbookVersionModel(
            version_id=version_id,
            workbook_id=wb.workbook_id,
            spreadsheet_id=graph.spreadsheet_id,
            parent_version_id=parent_version_id,
            version_seq_num=version_seq_num,
            sha256_hash=graph.sha256_hash,
            gcs_snapshot_uri=gcs_snapshot_uri,
            committed_by_google_user=who_google_user,
            committed_by_iam_principal=who_iam_principal,
            commit_comment=commit_comment,
            total_sheets=len(graph.sheets),
            total_populated_cells=len(graph.cells),
            total_formula_cells=total_formulas,
            total_dag_edges=len(graph.dag_edges),
            structural_mutation_count=structural_mutation_count,
            manual_override_count=manual_override_count,
        )
        self.session.add(v_model)
        await self.session.flush()

        # Bulk insert worksheets
        if graph.sheets:
            await self.session.execute(
                insert(WorksheetModel),
                [
                    {
                        "worksheet_id": f"{version_id}:{s.sheet_index}",
                        "version_id": version_id,
                        "sheet_index": s.sheet_index,
                        "sheet_name": s.sheet_name,
                        "visibility": s.visibility,
                        "populated_cell_count": s.populated_cell_count,
                        "formula_cell_count": s.formula_cell_count,
                        "shared_formula_count": s.shared_formula_count,
                    }
                    for s in graph.sheets
                ],
            )

        # Bulk insert cells in batches of 5,000 for SQLite/PostgreSQL parameter limit safety
        cell_dicts = [
            {
                "cell_id": f"{version_id}:{c.sheet_name}!{c.cell_coord}",
                "version_id": version_id,
                "sheet_name": c.sheet_name,
                "cell_coord": c.cell_coord,
                "row_num": c.row_num,
                "col_num": c.col_num,
                "col_letter": c.col_letter,
                "data_type": c.data_type,
                "raw_value": c.raw_value,
                "numeric_value": c.numeric_value,
                "raw_formula": c.raw_formula,
                "canonical_formula": c.canonical_formula,
                "r1c1_formula": c.r1c1_formula,
                "formula_hash": c.formula_hash,
                "shared_group_index": c.shared_group_index,
                "is_shared_master": c.is_shared_master,
                "semantic_role": c.semantic_role.value,
            }
            for c in graph.cells
        ]
        for i in range(0, len(cell_dicts), 5000):
            await self.session.execute(insert(CellModel), cell_dicts[i : i + 5000])

        # Bulk insert DAG edges in batches of 5,000
        edge_dicts = [
            {
                "edge_id": f"{version_id}:e:{idx}",
                "version_id": version_id,
                "precedent_sheet": e.precedent_sheet,
                "precedent_coord": e.precedent_coord,
                "dependent_sheet": e.dependent_sheet,
                "dependent_coord": e.dependent_coord,
                "reference_type": e.reference_type,
            }
            for idx, e in enumerate(graph.dag_edges)
        ]
        for i in range(0, len(edge_dicts), 5000):
            await self.session.execute(insert(CellDependencyEdgeModel), edge_dicts[i : i + 5000])

        # Bulk insert named ranges
        if graph.named_ranges:
            nr_dicts = [
                {
                    "named_range_id": f"{version_id}:nr:{idx}",
                    "version_id": version_id,
                    "name": nr.name,
                    "local_sheet_id": nr.local_sheet_id,
                    "scope_sheet_name": nr.scope_sheet_name,
                    "refers_to": nr.refers_to,
                    "is_broken_ref": nr.is_broken_ref,
                    "hidden": nr.hidden,
                }
                for idx, nr in enumerate(graph.named_ranges)
            ]
            for i in range(0, len(nr_dicts), 2000):
                await self.session.execute(insert(NamedRangeModel), nr_dicts[i : i + 2000])

        # Bulk insert macro bindings
        if graph.macro_bindings:
            await self.session.execute(
                insert(MacroBindingModel),
                [
                    {
                        "binding_id": f"{version_id}:mb:{idx}",
                        "version_id": version_id,
                        "sheet_name": mb.sheet_name,
                        "anchor_cell": mb.anchor_cell,
                        "button_label": mb.button_label,
                        "macro_target": mb.macro_target,
                        "raw_macro_ref": mb.raw_macro_ref,
                    }
                    for idx, mb in enumerate(graph.macro_bindings)
                ],
            )

        # Bulk insert technical debt items
        if graph.technical_debt_items:
            debt_dicts = [
                {
                    "debt_id": f"{version_id}:td:{idx}",
                    "version_id": version_id,
                    "debt_category": td.debt_category,
                    "identifier": td.identifier,
                    "location": td.location,
                    "details": td.details,
                    "severity": td.severity,
                }
                for idx, td in enumerate(graph.technical_debt_items)
            ]
            for i in range(0, len(debt_dicts), 2000):
                await self.session.execute(insert(TechnicalDebtItemModel), debt_dicts[i : i + 2000])

        # Append immutable 4-Ws audit events
        await self.append_audit_events(audit_events)

    async def append_audit_events(self, events: list[AuditEventRecord]) -> None:
        """Append one or more 4-Ws AuditEventRecord rows to audit_events."""
        if not events:
            return
        await self.session.execute(
            insert(AuditEventModel),
            [
                {
                    "event_id": e.event_id,
                    "workbook_id": e.workbook_id,
                    "spreadsheet_id": e.spreadsheet_id,
                    "version_id": e.version_id,
                    "parent_version_id": e.parent_version_id,
                    "version_seq_num": e.version_seq_num,
                    "sheet_name": e.sheet_name,
                    "cell_coord": e.cell_coord,
                    "what_element_coord": e.what_element_coord,
                    "what_semantic_role": e.what_semantic_role.value,
                    "what_change_type": e.what_change_type.value,
                    "severity": e.severity.value,
                    "before_state": e.before_state,
                    "after_state": e.after_state,
                    "who_google_user": e.who_google_user,
                    "who_iam_principal": e.who_iam_principal,
                    "who_client_platform": e.who_client_platform,
                    "who_spreadsheet_id": e.who_spreadsheet_id,
                    "when_event_utc": e.when_event_utc,
                    "gcs_snapshot_uri": e.gcs_snapshot_uri,
                }
                for e in events
            ],
        )

    async def list_audit_events(
        self,
        spreadsheet_id: str,
        change_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query immutable 4-Ws audit_events for a spreadsheet_id."""
        stmt = select(AuditEventModel).where(AuditEventModel.spreadsheet_id == spreadsheet_id)
        if change_type:
            stmt = stmt.where(AuditEventModel.what_change_type == change_type)
        stmt = stmt.order_by(AuditEventModel.when_event_utc.desc())
        rows = (await self.session.execute(stmt)).scalars().all()
        return [
            {
                "event_id": r.event_id,
                "workbook_id": r.workbook_id,
                "spreadsheet_id": r.spreadsheet_id,
                "version_id": r.version_id,
                "parent_version_id": r.parent_version_id,
                "version_seq_num": r.version_seq_num,
                "sheet_name": r.sheet_name,
                "cell_coord": r.cell_coord,
                "what_element_coord": r.what_element_coord,
                "what_semantic_role": r.what_semantic_role,
                "what_change_type": r.what_change_type,
                "severity": r.severity,
                "before_state": r.before_state,
                "after_state": r.after_state,
                "who_google_user": r.who_google_user,
                "who_iam_principal": r.who_iam_principal,
                "who_client_platform": r.who_client_platform,
                "who_spreadsheet_id": r.who_spreadsheet_id,
                "when_event_utc": r.when_event_utc,
                "gcs_snapshot_uri": r.gcs_snapshot_uri,
            }
            for r in rows
        ]

    async def record_solver_telemetry(
        self,
        spreadsheet_id: str,
        workbook_id: str,
        macro_name: str,
        caller_google_user: str,
        solve_count: int,
        execution_time_ms: float,
        execution_engine: str,
        parity_mode: str,
        executed_at_utc: str,
    ) -> None:
        """Record a solver execution telemetry row."""
        await self.session.execute(
            insert(SolverRunTelemetryModel),
            [
                {
                    "run_id": str(uuid4()),
                    "spreadsheet_id": spreadsheet_id,
                    "workbook_id": workbook_id,
                    "macro_name": macro_name,
                    "caller_google_user": caller_google_user,
                    "solve_count": solve_count,
                    "execution_time_ms": execution_time_ms,
                    "execution_engine": execution_engine,
                    "parity_mode": parity_mode,
                    "executed_at_utc": executed_at_utc,
                }
            ],
        )

    async def list_versions(self, spreadsheet_id: str) -> list[WorkbookVersionModel]:
        """List committed versions for a spreadsheet_id ordered newest-first."""
        stmt = (
            select(WorkbookVersionModel)
            .where(WorkbookVersionModel.spreadsheet_id == spreadsheet_id)
            .order_by(WorkbookVersionModel.version_seq_num.desc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)

    async def list_technical_debt_items(self, version_id: str) -> list[dict[str, Any]]:
        """List cataloged technical debt items for a version_id."""
        stmt = select(TechnicalDebtItemModel).where(
            TechnicalDebtItemModel.version_id == version_id
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [
            {
                "debt_category": r.debt_category,
                "identifier": r.identifier,
                "location": r.location,
                "details": r.details,
                "severity": r.severity,
            }
            for r in rows
        ]

    async def get_lineage_subgraph(
        self,
        version_id: str,
        sheet_name: str,
        cell_coord: str,
        max_depth: int = 4,
    ) -> dict[str, Any]:
        """Traverse upstream precedents and downstream dependents in the persisted DAG."""
        stmt = select(CellDependencyEdgeModel).where(
            CellDependencyEdgeModel.version_id == version_id
        )
        all_edges = (await self.session.execute(stmt)).scalars().all()
        edge_records = [
            DependencyEdgeRecord(
                precedent_sheet=e.precedent_sheet,
                precedent_coord=e.precedent_coord,
                dependent_sheet=e.dependent_sheet,
                dependent_coord=e.dependent_coord,
                reference_type=e.reference_type,
            )
            for e in all_edges
        ]
        from src.parser.dag_builder import DependencyDAGBuilder

        downstream = DependencyDAGBuilder.trace_downstream_dependents(
            edges=edge_records,
            sheet_name=sheet_name,
            cell_coord=cell_coord,
            max_depth=max_depth,
        )
        upstream = [
            {
                "sheet_name": e.precedent_sheet,
                "cell_coord": e.precedent_coord,
                "reference_type": e.reference_type,
            }
            for e in edge_records
            if e.dependent_sheet == sheet_name and e.dependent_coord == cell_coord
        ]
        return {
            "version_id": version_id,
            "sheet_name": sheet_name,
            "cell_coord": cell_coord,
            "upstream_precedents": upstream,
            "downstream_dependents": downstream,
        }

