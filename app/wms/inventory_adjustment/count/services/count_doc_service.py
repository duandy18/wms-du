from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.wms.inventory_adjustment.count.contracts.count_doc import (
    CountDocCreateIn,
    CountDocDetailOut,
    CountDocFreezeOut,
    CountDocLineOut,
    CountDocLinesUpdateIn,
    CountDocLinesUpdateOut,
    CountDocListOut,
    CountDocOut,
    CountDocPostOut,
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
    def _sorted_lot_snapshots(line) -> list:
        return sorted(
            list(getattr(line, "lot_snapshots", []) or []),
            key=lambda x: (-int(x.snapshot_qty_base), int(x.lot_id), int(x.id)),
        )

    @staticmethod
    def _line_meta(
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
        if getattr(line, "reason_code", None):
            meta["reason_code"] = str(line.reason_code)
        if getattr(line, "disposition", None):
            meta["disposition"] = str(line.disposition)
        if getattr(line, "remark", None):
            meta["remark"] = str(line.remark)
        if str(sub_reason) == "COUNT_CONFIRM":
            meta["allow_zero_delta_ledger"] = True
        return meta

    @staticmethod
    def _zero_stats() -> dict[str, int]:
        return {
            "line_count": 0,
            "diff_line_count": 0,
            "diff_qty_base_total": 0,
        }

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

    async def create_doc(
        self,
        session: AsyncSession,
        *,
        payload: CountDocCreateIn,
        actor_user_id: int | None,
    ) -> CountDocOut:
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

    async def get_doc_detail(
        self,
        session: AsyncSession,
        *,
        doc_id: int,
    ) -> CountDocDetailOut:
        doc = await self.repo.get_doc_detail(session, doc_id=int(doc_id))
        if doc is None:
            raise LookupError(f"count_doc_not_found:{int(doc_id)}")

        stats_map = await self.repo.get_doc_line_stats(session, doc_ids=[int(doc.id)])
        event_ids = [int(doc.posted_event_id)] if doc.posted_event_id is not None else []
        event_map = await self.repo.get_posted_event_briefs(session, event_ids=event_ids)

        base = self._build_count_doc_out(doc, stats_map=stats_map, event_map=event_map)
        return CountDocDetailOut(
            **base.model_dump(),
            lines=[CountDocLineOut.model_validate(x) for x in doc.lines],
        )

    async def list_docs(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> CountDocListOut:
        total, docs = await self.repo.list_docs(
            session,
            warehouse_id=int(warehouse_id) if warehouse_id is not None else None,
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

        updated_count = await self.repo.update_line_counts(
            session,
            doc_id=int(doc_id),
            lines=[
                {
                    "line_id": int(x.line_id),
                    "counted_item_uom_id": int(x.counted_item_uom_id),
                    "counted_qty_input": int(x.counted_qty_input),
                    "reason_code": x.reason_code,
                    "disposition": x.disposition,
                    "remark": x.remark,
                }
                for x in payload.lines
            ],
        )

        _ = await self.repo.try_mark_doc_counted(session, doc_id=int(doc_id))
        session.expire_all()
        detail = await self.repo.get_doc_detail(session, doc_id=int(doc_id))
        if detail is None:
            raise LookupError(f"count_doc_not_found_after_update:{int(doc_id)}")

        return CountDocLinesUpdateOut(
            doc_id=int(detail.id),
            status=str(detail.status),  # type: ignore[arg-type]
            updated_count=int(updated_count),
            lines=[x for x in CountDocDetailOut.model_validate(detail).lines],
        )

    async def _post_line_diff(
        self,
        session: AsyncSession,
        *,
        doc,
        line,
        event_id: int,
        event_no: str,
        posted_at: datetime,
        trace_id: str,
    ) -> int:
        snapshots = self._sorted_lot_snapshots(line)
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

        detail_out = await self.get_doc_detail(session, doc_id=int(doc_id))

        if not list(detail_out.lines or []):
            raise ValueError(f"count_doc_post_requires_lines: doc_id={int(detail_out.id)}")

        for line in detail_out.lines:
            if line.counted_qty_base is None or line.diff_qty_base is None:
                raise ValueError(f"count_doc_post_requires_all_lines_counted: line_id={int(line.id)}")

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
                "warehouse_id": int(detail_out.warehouse_id),
                "source_ref": str(detail_out.count_no),
                "occurred_at": posted_at,
                "trace_id": str(trace_id),
                "created_by": (int(detail_out.created_by) if detail_out.created_by is not None else None),
                "remark": (str(detail_out.remark).strip() if detail_out.remark else f"post count doc {detail_out.count_no}"),
            },
        )
        event_id = int(row.scalar_one())

        for line in detail_out.lines:
            await self._post_line_diff(
                session,
                doc=detail_out,
                line=line,
                event_id=int(event_id),
                event_no=str(event_no),
                posted_at=posted_at,
                trace_id=str(trace_id),
            )

        await self.repo.mark_doc_posted(
            session,
            doc_id=int(detail_out.id),
            posted_event_id=int(event_id),
            posted_at=posted_at,
        )
        session.expire_all()

        return CountDocPostOut(
            doc_id=int(detail_out.id),
            status="POSTED",
            posted_event_id=int(event_id),
            posted_at=posted_at,
        )


__all__ = [
    "CountDocService",
]
