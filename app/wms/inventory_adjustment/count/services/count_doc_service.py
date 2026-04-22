from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.inventory_adjustment.count.contracts.count_doc import (
    CountDocCreateIn,
    CountDocDetailOut,
    CountDocFreezeOut,
    CountDocLinesUpdateIn,
    CountDocLinesUpdateOut,
    CountDocListOut,
    CountDocOut,
    CountDocPostOut,
)
from app.wms.inventory_adjustment.count.repos.count_doc_repo import CountDocRepo


class CountDocService:
    def __init__(self, *, repo: CountDocRepo | None = None) -> None:
        self.repo = repo or CountDocRepo()

    def _make_count_no(self, now: datetime | None = None) -> str:
        ts = (now or datetime.now(timezone.utc)).strftime("%Y%m%d%H%M%S")
        suffix = uuid4().hex[:8].upper()
        return f"CTD-{ts}-{suffix}"

    async def _require_doc(self, session: AsyncSession, *, doc_id: int):
        doc = await self.repo.get_doc(session, doc_id=int(doc_id))
        if doc is None:
            raise LookupError(f"count_doc_not_found:{int(doc_id)}")
        return doc

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
        return CountDocOut.model_validate(doc)

    async def get_doc_detail(
        self,
        session: AsyncSession,
        *,
        doc_id: int,
    ) -> CountDocDetailOut:
        doc = await self.repo.get_doc_detail(session, doc_id=int(doc_id))
        if doc is None:
            raise LookupError(f"count_doc_not_found:{int(doc_id)}")
        return CountDocDetailOut.model_validate(doc)

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
        return CountDocListOut(
            total=int(total),
            items=[CountDocOut.model_validate(x) for x in docs],
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
        detail = await self.repo.get_doc_detail(session, doc_id=int(doc_id))
        if detail is None:
            raise LookupError(f"count_doc_not_found_after_update:{int(doc_id)}")

        return CountDocLinesUpdateOut(
            doc_id=int(detail.id),
            status=str(detail.status),  # type: ignore[arg-type]
            updated_count=int(updated_count),
            lines=[x for x in CountDocDetailOut.model_validate(detail).lines],
        )

    async def post_doc(
        self,
        session: AsyncSession,
        *,
        doc_id: int,
    ) -> CountDocPostOut:
        _ = session
        _ = doc_id
        raise RuntimeError(
            "count_doc_post_not_ready: COUNT wms_events / ledger posting chain is not implemented yet."
        )


__all__ = [
    "CountDocService",
]
