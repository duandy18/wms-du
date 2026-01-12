# app/api/routers/stock_ledger_routes_query.py
from __future__ import annotations

from datetime import timezone

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.stock_ledger import StockLedger
from app.schemas.stock_ledger import (
    LedgerEnums,
    LedgerList,
    LedgerRow,
    LedgerQuery,
    ReasonCanon,
    SubReason,
)
from app.api.routers.stock_ledger_helpers import (
    build_base_ids_stmt,
    infer_movement_type,
    normalize_time_range,
)

UTC = timezone.utc


def register(router: APIRouter) -> None:
    @router.post("/enums", response_model=LedgerEnums)
    async def ledger_enums() -> LedgerEnums:
        """
        前端下拉唯一来源（由后端 Enum 生成）：
        - reason_canons: 稳定口径枚举
        - sub_reasons: 具体动作枚举
        """
        return LedgerEnums(
            reason_canons=list(ReasonCanon),
            sub_reasons=list(SubReason),
        )

    @router.post("/query", response_model=LedgerList)
    async def query_ledger(
        payload: LedgerQuery,
        session: AsyncSession = Depends(get_session),
    ) -> LedgerList:
        """
        普通查询（<=90 天限制由 normalize_time_range 控制）：
        - 默认按 occurred_at 降序 + id 降序排序；
        - 支持 item_id/item_keyword/warehouse_id/batch_code/reason/reason_canon/sub_reason/ref/trace_id 过滤；
        - 返回 item_name（当前页批量补齐）。
        """
        time_from, time_to = normalize_time_range(payload)

        # ✅ 过滤合同统一收敛到 helper（build_common_filters -> build_base_ids_stmt）
        ids_stmt = build_base_ids_stmt(payload, time_from, time_to)
        ids_subq = ids_stmt.subquery()

        total = (await session.execute(select(func.count()).select_from(ids_subq))).scalar_one()

        list_stmt = (
            select(StockLedger)
            .where(StockLedger.id.in_(select(ids_subq.c.id)))
            .order_by(StockLedger.occurred_at.desc(), StockLedger.id.desc())
            .limit(payload.limit)
            .offset(payload.offset)
        )
        rows: list[StockLedger] = (await session.execute(list_stmt)).scalars().all()

        # 便民：批量补齐 item_name（当前页）
        item_ids = sorted({int(r.item_id) for r in rows if r.item_id is not None})
        item_name_map: dict[int, str] = {}
        if item_ids:
            res = await session.execute(
                sa.text(
                    """
                    SELECT id, name
                      FROM items
                     WHERE id = ANY(:ids)
                    """
                ),
                {"ids": item_ids},
            )
            for x in res.mappings().all():
                iid = int(x["id"])
                nm = str(x["name"] or "").strip()
                if nm:
                    item_name_map[iid] = nm

        return LedgerList(
            total=total,
            items=[
                LedgerRow(
                    id=r.id,
                    delta=r.delta,
                    reason=r.reason,
                    reason_canon=r.reason_canon,
                    sub_reason=r.sub_reason,
                    ref=r.ref,
                    ref_line=r.ref_line,
                    occurred_at=r.occurred_at,
                    created_at=r.created_at,
                    after_qty=r.after_qty,
                    item_id=r.item_id,
                    item_name=item_name_map.get(int(r.item_id)) if r.item_id is not None else None,
                    warehouse_id=r.warehouse_id,
                    batch_code=r.batch_code,
                    trace_id=r.trace_id,
                    movement_type=infer_movement_type(r.reason),
                )
                for r in rows
            ],
        )
