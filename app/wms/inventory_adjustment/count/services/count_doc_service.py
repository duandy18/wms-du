from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.wms.inventory_adjustment.count.contracts.count_doc import (
    CountDocCreateIn,
    CountDocFreezeOut,
    CountDocLinesUpdateIn,
    CountDocLinesUpdateOut,
    CountDocListOut,
    CountDocOut,
    CountDocPostIn,
    CountDocPostOut,
    CountDocVoidOut,
)
from app.wms.inventory_adjustment.count.contracts.count_doc_execution import (
    CountDocExecutionDetailOut,
    CountDocExecutionLineOut,
)
from app.wms.inventory_adjustment.count.repos.count_doc_repo import CountDocRepo
from app.wms.stock.services.stock_service import StockService


class CountDocService:
    def __init__(
        self,
        *,
        repo: CountDocRepo | None = None,
        stock: StockService | None = None,
    ) -> None:
        self.repo = repo or CountDocRepo()
        self.stock = stock or StockService()

    def _make_count_no(self, now: datetime | None = None) -> str:
        ts = (now or datetime.now(timezone.utc)).strftime("%Y%m%d%H%M%S")
        suffix = uuid4().hex[:8].upper()
        return f"CTD-{ts}-{suffix}"

    def _make_count_event_no(self, now: datetime | None = None) -> str:
        ts = (now or datetime.now(timezone.utc)).strftime("%Y%m%d%H%M%S")
        suffix = uuid4().hex[:8].upper()
        return f"CNT-{ts}-{suffix}"

    def _make_trace_id(self) -> str:
        return f"COUNT-POST-{uuid4().hex[:20].upper()}"

    async def _require_doc(self, session: AsyncSession, *, doc_id: int):
        doc = await self.repo.get_doc(session, doc_id=int(doc_id))
        if doc is None:
            raise LookupError(f"count_doc_not_found:{int(doc_id)}")
        return doc

    @staticmethod
    def _sorted_lot_snapshots(source) -> list:
        rows = source if isinstance(source, list) else list(getattr(source, "lot_snapshots", []) or [])
        return sorted(
            list(rows),
            key=lambda x: (-int(x.snapshot_qty_base), int(x.lot_id), int(x.id)),
        )

    @staticmethod
    def _zero_stats() -> dict[str, int]:
        return {
            "line_count": 0,
            "diff_line_count": 0,
            "diff_qty_base_total": 0,
        }

    @staticmethod
    def _normalize_name(value: str | None) -> str | None:
        if value is None:
            return None
        x = str(value).strip()
        return x or None

    def _line_meta(
        self,
        *,
        doc,
        line,
        event_id: int,
        sub_reason: str,
    ) -> dict[str, object]:
        meta: dict[str, object] = {
            "sub_reason": str(sub_reason),
            "count_doc_id": int(doc.id),
            "count_doc_line_id": int(line.id),
            "count_no": str(doc.count_no),
            "event_id": int(event_id),
        }
        if getattr(doc, "counted_by_name_snapshot", None):
            meta["counted_by_name_snapshot"] = str(doc.counted_by_name_snapshot)
        if getattr(doc, "reviewed_by_name_snapshot", None):
            meta["reviewed_by_name_snapshot"] = str(doc.reviewed_by_name_snapshot)
        if str(sub_reason) == "COUNT_CONFIRM":
            meta["allow_zero_delta_ledger"] = True
        return meta

    def _build_count_doc_out(
        self,
        doc,
        *,
        stats_map: dict[int, dict[str, int]],
        event_map: dict[int, dict[str, object]],
    ) -> CountDocOut:
        stats = stats_map.get(int(doc.id), self._zero_stats())
        event = (
            event_map.get(int(doc.posted_event_id))
            if getattr(doc, "posted_event_id", None) is not None
            else None
        ) or {}

        return CountDocOut(
            id=int(doc.id),
            count_no=str(doc.count_no),
            warehouse_id=int(doc.warehouse_id),
            snapshot_at=doc.snapshot_at,
            status=str(doc.status),  # type: ignore[arg-type]
            posted_event_id=(int(doc.posted_event_id) if doc.posted_event_id is not None else None),
            created_by=(int(doc.created_by) if doc.created_by is not None else None),
            counted_by_name_snapshot=self._normalize_name(getattr(doc, "counted_by_name_snapshot", None)),
            reviewed_by_name_snapshot=self._normalize_name(getattr(doc, "reviewed_by_name_snapshot", None)),
            remark=doc.remark,
            created_at=doc.created_at,
            counted_at=doc.counted_at,
            posted_at=doc.posted_at,
            line_count=int(stats["line_count"]),
            diff_line_count=int(stats["diff_line_count"]),
            diff_qty_base_total=int(stats["diff_qty_base_total"]),
            posted_event_no=(str(event["event_no"]) if event.get("event_no") is not None else None),
            posted_event_type=(str(event["event_type"]) if event.get("event_type") is not None else None),
            posted_source_type=(str(event["source_type"]) if event.get("source_type") is not None else None),
            posted_event_kind=(str(event["event_kind"]) if event.get("event_kind") is not None else None),
            posted_event_status=(str(event["status"]) if event.get("status") is not None else None),
        )

    async def _build_execution_line_outs(
        self,
        session: AsyncSession,
        *,
        lines: list,
    ) -> list[CountDocExecutionLineOut]:
        item_ids = [int(x.item_id) for x in lines]
        base_uom_map = await self.repo.get_base_uom_map(session, item_ids=item_ids)

        out: list[CountDocExecutionLineOut] = []
        for line in lines:
            base_uom = base_uom_map.get(int(line.item_id), {})
            out.append(
                CountDocExecutionLineOut(
                    id=int(line.id),
                    line_no=int(line.line_no),
                    item_id=int(line.item_id),
                    item_name_snapshot=line.item_name_snapshot,
                    item_spec_snapshot=line.item_spec_snapshot,
                    snapshot_qty_base=int(line.snapshot_qty_base),
                    base_item_uom_id=(
                        int(base_uom["base_item_uom_id"])
                        if base_uom.get("base_item_uom_id") is not None
                        else None
                    ),
                    base_uom_name=(
                        str(base_uom["base_uom_name"])
                        if base_uom.get("base_uom_name") is not None
                        else None
                    ),
                    counted_qty_input=(
                        int(line.counted_qty_input)
                        if line.counted_qty_input is not None
                        else None
                    ),
                    counted_qty_base=(
                        int(line.counted_qty_base)
                        if line.counted_qty_base is not None
                        else None
                    ),
                    diff_qty_base=(
                        int(line.diff_qty_base)
                        if line.diff_qty_base is not None
                        else None
                    ),
                )
            )
        return out

    async def create_doc(
        self,
        session: AsyncSession,
        *,
        payload: CountDocCreateIn,
        actor_user_id: int | None,
    ) -> CountDocOut:
        active = await self.repo.get_active_doc_by_warehouse(
            session,
            warehouse_id=int(payload.warehouse_id),
        )
        if active is not None:
            raise ValueError(
                f"count_doc_active_exists: warehouse_id={int(payload.warehouse_id)}, "
                f"doc_id={int(active.id)}, count_no={str(active.count_no)}, status={str(active.status)}"
            )

        count_no = self._make_count_no(payload.snapshot_at)

        doc = await self.repo.create_doc(
            session,
            count_no=count_no,
            warehouse_id=int(payload.warehouse_id),
            snapshot_at=payload.snapshot_at,
            created_by=int(actor_user_id) if actor_user_id is not None else None,
            remark=payload.remark,
        )
        await session.flush()
        return self._build_count_doc_out(doc, stats_map={}, event_map={})

    async def get_doc_execution_detail(
        self,
        session: AsyncSession,
        *,
        doc_id: int,
    ) -> CountDocExecutionDetailOut:
        doc = await self.repo.get_doc_detail(
            session,
            doc_id=int(doc_id),
            include_lot_snapshots=False,
        )
        if doc is None:
            raise LookupError(f"count_doc_not_found:{int(doc_id)}")

        stats_map = await self.repo.get_doc_line_stats(session, doc_ids=[int(doc.id)])
        stats = stats_map.get(int(doc.id), self._zero_stats())
        line_outs = await self._build_execution_line_outs(session, lines=list(doc.lines or []))

        return CountDocExecutionDetailOut(
            id=int(doc.id),
            count_no=str(doc.count_no),
            warehouse_id=int(doc.warehouse_id),
            snapshot_at=doc.snapshot_at,
            status=str(doc.status),  # type: ignore[arg-type]
            counted_by_name_snapshot=self._normalize_name(getattr(doc, "counted_by_name_snapshot", None)),
            reviewed_by_name_snapshot=self._normalize_name(getattr(doc, "reviewed_by_name_snapshot", None)),
            created_at=doc.created_at,
            counted_at=doc.counted_at,
            posted_at=doc.posted_at,
            line_count=int(stats["line_count"]),
            diff_line_count=int(stats["diff_line_count"]),
            diff_qty_base_total=int(stats["diff_qty_base_total"]),
            lines=line_outs,
        )

    async def list_docs(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int | None = None,
        active_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> CountDocListOut:
        total, docs = await self.repo.list_docs(
            session,
            warehouse_id=int(warehouse_id) if warehouse_id is not None else None,
            active_only=bool(active_only),
            limit=int(limit),
            offset=int(offset),
        )

        doc_ids = [int(x.id) for x in docs]
        stats_map = await self.repo.get_doc_line_stats(session, doc_ids=doc_ids)

        event_ids = [int(x.posted_event_id) for x in docs if x.posted_event_id is not None]
        event_map = await self.repo.get_posted_event_briefs(session, event_ids=event_ids)

        return CountDocListOut(
            total=int(total),
            items=[self._build_count_doc_out(x, stats_map=stats_map, event_map=event_map) for x in docs],
        )

    async def freeze_doc(
        self,
        session: AsyncSession,
        *,
        doc_id: int,
    ) -> CountDocFreezeOut:
        doc = await self._require_doc(session, doc_id=int(doc_id))

        if str(doc.status) != "DRAFT":
            raise ValueError(f"count_doc_freeze_requires_draft: current={doc.status}")

        line_count, lot_snapshot_count = await self.repo.freeze_doc_lines_from_current_stock(
            session,
            doc_id=int(doc_id),
        )

        return CountDocFreezeOut(
            doc_id=int(doc_id),
            status="FROZEN",
            snapshot_at=doc.snapshot_at,
            line_count=int(line_count),
            lot_snapshot_count=int(lot_snapshot_count),
        )

    async def update_doc_lines(
        self,
        session: AsyncSession,
        *,
        doc_id: int,
        payload: CountDocLinesUpdateIn,
    ) -> CountDocLinesUpdateOut:
        doc = await self._require_doc(session, doc_id=int(doc_id))

        if str(doc.status) not in {"FROZEN", "COUNTED"}:
            raise ValueError(
                f"count_doc_lines_update_requires_frozen_or_counted: current={doc.status}"
            )

        counted_by_name = self._normalize_name(payload.counted_by_name_snapshot)
        if not counted_by_name:
            raise ValueError("count_doc_lines_update_requires_counted_by_name_snapshot")

        updated_count = await self.repo.update_line_counts(
            session,
            doc_id=int(doc_id),
            counted_by_name_snapshot=counted_by_name,
            lines=[
                {
                    "line_id": int(x.line_id),
                    "counted_qty_input": int(x.counted_qty_input),
                }
                for x in payload.lines
            ],
        )

        _ = await self.repo.try_mark_doc_counted(session, doc_id=int(doc_id))
        session.expire_all()
        detail_model = await self.repo.get_doc_detail(
            session,
            doc_id=int(doc_id),
            include_lot_snapshots=False,
        )
        if detail_model is None:
            raise LookupError(f"count_doc_not_found_after_update:{int(doc_id)}")

        line_outs = await self._build_execution_line_outs(
            session,
            lines=list(detail_model.lines or []),
        )

        return CountDocLinesUpdateOut(
            doc_id=int(detail_model.id),
            status=str(detail_model.status),  # type: ignore[arg-type]
            updated_count=int(updated_count),
            lines=line_outs,
        )

    async def _post_line_diff(
        self,
        session: AsyncSession,
        *,
        doc,
        line,
        snapshots: list,
        event_id: int,
        event_no: str,
        posted_at: datetime,
        trace_id: str,
    ) -> int:
        rows = await session.execute(
            text(
                """
                SELECT
                  id,
                  line_id,
                  lot_id,
                  lot_code_snapshot,
                  snapshot_qty_base,
                  created_at
                FROM count_doc_line_lot_snapshots
                WHERE line_id = :line_id
                ORDER BY
                  snapshot_qty_base DESC,
                  lot_id ASC,
                  id ASC
                """
            ),
            {"line_id": int(line.id)},
        )
        snapshots = [
            SimpleNamespace(
                id=int(row["id"]),
                line_id=int(row["line_id"]),
                lot_id=int(row["lot_id"]),
                lot_code_snapshot=row["lot_code_snapshot"],
                snapshot_qty_base=int(row["snapshot_qty_base"]),
                created_at=row["created_at"],
            )
            for row in rows.mappings().all()
        ]
        snapshots = self._sorted_lot_snapshots(snapshots)
        if not snapshots:
            raise RuntimeError(f"count_doc_post_missing_lot_snapshots: line_id={int(line.id)}")

        diff_qty_base = int(line.diff_qty_base or 0)
        line_no = int(line.line_no)

        if diff_qty_base == 0:
            target = snapshots[0]
            await self.stock.adjust_lot(
                session=session,
                item_id=int(line.item_id),
                warehouse_id=int(doc.warehouse_id),
                lot_id=int(target.lot_id),
                delta=0,
                reason=MovementType.COUNT,
                ref=str(event_no),
                ref_line=line_no,
                occurred_at=posted_at,
                batch_code=target.lot_code_snapshot,
                production_date=None,
                expiry_date=None,
                trace_id=str(trace_id),
                meta=self._line_meta(
                    doc=doc,
                    line=line,
                    event_id=int(event_id),
                    sub_reason="COUNT_CONFIRM",
                ),
                shadow_write_stocks=False,
            )
            return 1

        if diff_qty_base > 0:
            target = snapshots[0]
            await self.stock.adjust_lot(
                session=session,
                item_id=int(line.item_id),
                warehouse_id=int(doc.warehouse_id),
                lot_id=int(target.lot_id),
                delta=int(diff_qty_base),
                reason=MovementType.COUNT,
                ref=str(event_no),
                ref_line=line_no,
                occurred_at=posted_at,
                batch_code=target.lot_code_snapshot,
                production_date=None,
                expiry_date=None,
                trace_id=str(trace_id),
                meta=self._line_meta(
                    doc=doc,
                    line=line,
                    event_id=int(event_id),
                    sub_reason="COUNT_ADJUST",
                ),
                shadow_write_stocks=False,
            )
            return 1

        remaining = int(-diff_qty_base)
        written = 0

        for snap in snapshots:
            if remaining <= 0:
                break

            snap_qty = int(snap.snapshot_qty_base)
            if snap_qty <= 0:
                continue

            consume = min(remaining, snap_qty)
            if consume <= 0:
                continue

            await self.stock.adjust_lot(
                session=session,
                item_id=int(line.item_id),
                warehouse_id=int(doc.warehouse_id),
                lot_id=int(snap.lot_id),
                delta=-int(consume),
                reason=MovementType.COUNT,
                ref=str(event_no),
                ref_line=line_no,
                occurred_at=posted_at,
                batch_code=snap.lot_code_snapshot,
                production_date=None,
                expiry_date=None,
                trace_id=str(trace_id),
                meta=self._line_meta(
                    doc=doc,
                    line=line,
                    event_id=int(event_id),
                    sub_reason="COUNT_ADJUST",
                ),
                shadow_write_stocks=False,
            )
            remaining -= int(consume)
            written += 1

        if remaining != 0:
            raise RuntimeError(
                f"count_doc_post_unallocated_negative_diff: line_id={int(line.id)}, remaining={int(remaining)}"
            )

        return int(written)

    async def post_doc(
        self,
        session: AsyncSession,
        *,
        doc_id: int,
        payload: CountDocPostIn,
    ) -> CountDocPostOut:
        doc = await self._require_doc(session, doc_id=int(doc_id))

        if str(doc.status) == "POSTED":
            if doc.posted_event_id is None or doc.posted_at is None:
                raise RuntimeError(f"count_doc_posted_missing_bridge_fields:{int(doc_id)}")
            return CountDocPostOut(
                doc_id=int(doc.id),
                status="POSTED",
                posted_event_id=int(doc.posted_event_id),
                posted_at=doc.posted_at,
            )

        if str(doc.status) != "COUNTED":
            raise ValueError(f"count_doc_post_requires_counted: current={doc.status}")

        reviewed_by_name = self._normalize_name(payload.reviewed_by_name_snapshot)
        if not reviewed_by_name:
            raise ValueError("count_doc_post_requires_reviewed_by_name_snapshot")

        await self.repo.set_reviewed_by_name_snapshot(
            session,
            doc_id=int(doc_id),
            reviewed_by_name_snapshot=reviewed_by_name,
        )
        session.expire_all()

        doc_model = await self.repo.get_doc_detail(
            session,
            doc_id=int(doc_id),
            include_lot_snapshots=False,
        )
        if doc_model is None:
            raise LookupError(f"count_doc_not_found:{int(doc_id)}")

        if not self._normalize_name(doc_model.counted_by_name_snapshot):
            raise ValueError("count_doc_post_requires_counted_by_name_snapshot")
        if not self._normalize_name(doc_model.reviewed_by_name_snapshot):
            raise ValueError("count_doc_post_requires_reviewed_by_name_snapshot")

        orm_lines = list(doc_model.lines or [])
        if not orm_lines:
            raise ValueError(f"count_doc_post_requires_lines: doc_id={int(doc_model.id)}")

        for line in orm_lines:
            if line.counted_qty_base is None or line.diff_qty_base is None:
                raise ValueError(f"count_doc_post_requires_all_lines_counted: line_id={int(line.id)}")

        doc_ctx = SimpleNamespace(
            id=int(doc_model.id),
            count_no=str(doc_model.count_no),
            warehouse_id=int(doc_model.warehouse_id),
            created_by=(int(doc_model.created_by) if doc_model.created_by is not None else None),
            remark=doc_model.remark,
            counted_by_name_snapshot=self._normalize_name(doc_model.counted_by_name_snapshot),
            reviewed_by_name_snapshot=self._normalize_name(doc_model.reviewed_by_name_snapshot),
        )

        lines_ctx = [
            SimpleNamespace(
                id=int(line.id),
                line_no=int(line.line_no),
                item_id=int(line.item_id),
                diff_qty_base=(int(line.diff_qty_base) if line.diff_qty_base is not None else None),
                counted_qty_base=(int(line.counted_qty_base) if line.counted_qty_base is not None else None),
            )
            for line in orm_lines
        ]

        posted_at = datetime.now(timezone.utc)
        trace_id = self._make_trace_id()
        event_no = self._make_count_event_no(posted_at)

        row = await session.execute(
            text(
                """
                INSERT INTO wms_events (
                  event_no,
                  event_type,
                  warehouse_id,
                  source_type,
                  source_ref,
                  occurred_at,
                  trace_id,
                  event_kind,
                  target_event_id,
                  status,
                  created_by,
                  remark
                )
                VALUES (
                  :event_no,
                  'COUNT',
                  :warehouse_id,
                  'MANUAL_COUNT',
                  :source_ref,
                  :occurred_at,
                  :trace_id,
                  'COMMIT',
                  NULL,
                  'COMMITTED',
                  :created_by,
                  :remark
                )
                RETURNING id
                """
            ),
            {
                "event_no": str(event_no),
                "warehouse_id": int(doc_ctx.warehouse_id),
                "source_ref": str(doc_ctx.count_no),
                "occurred_at": posted_at,
                "trace_id": str(trace_id),
                "created_by": doc_ctx.created_by,
                "remark": (
                    str(doc_ctx.remark).strip()
                    if doc_ctx.remark
                    else f"post count doc {doc_ctx.count_no}"
                ),
            },
        )
        event_id = int(row.scalar_one())

        for line in lines_ctx:
            snapshots = await self.repo.get_line_lot_snapshots(
                session,
                line_id=int(line.id),
            )
            await self._post_line_diff(
                session,
                doc=doc_ctx,
                line=line,
                snapshots=snapshots,
                event_id=int(event_id),
                event_no=str(event_no),
                posted_at=posted_at,
                trace_id=str(trace_id),
            )

        await self.repo.mark_doc_posted(
            session,
            doc_id=int(doc_ctx.id),
            posted_event_id=int(event_id),
            posted_at=posted_at,
        )
        session.expire_all()

        return CountDocPostOut(
            doc_id=int(doc_ctx.id),
            status="POSTED",
            posted_event_id=int(event_id),
            posted_at=posted_at,
        )

    async def void_doc(
        self,
        session: AsyncSession,
        *,
        doc_id: int,
    ) -> CountDocVoidOut:
        doc = await self._require_doc(session, doc_id=int(doc_id))

        if str(doc.status) == "POSTED":
            raise ValueError("count_doc_void_forbidden_after_posted")

        await self.repo.mark_doc_voided(session, doc_id=int(doc_id))
        return CountDocVoidOut(
            doc_id=int(doc_id),
            status="VOIDED",
        )


__all__ = [
    "CountDocService",
]
