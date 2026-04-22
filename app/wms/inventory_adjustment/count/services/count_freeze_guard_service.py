from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.inventory_adjustment.count.repos.count_freeze_guard_repo import (
    get_frozen_count_doc_brief,
)


async def ensure_warehouse_not_frozen(
    session: AsyncSession,
    *,
    warehouse_id: int,
) -> None:
    frozen = await get_frozen_count_doc_brief(
        session,
        warehouse_id=int(warehouse_id),
    )
    if frozen is None:
        return

    raise HTTPException(
        status_code=409,
        detail={
            "error_code": "count_doc_frozen_for_warehouse",
            "warehouse_id": int(warehouse_id),
            "count_doc_id": int(frozen["id"]),
            "count_no": str(frozen["count_no"]),
            "snapshot_at": frozen["snapshot_at"].isoformat()
            if hasattr(frozen["snapshot_at"], "isoformat")
            else str(frozen["snapshot_at"]),
            "message": "该仓存在 FROZEN 状态盘点单，当前禁止任何会改库存的操作。",
        },
    )


__all__ = [
    "ensure_warehouse_not_frozen",
]
