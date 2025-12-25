# app/services/snapshot_service.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.snapshot_inventory import query_inventory_snapshot, query_inventory_snapshot_paged
from app.services.snapshot_item_detail import query_item_detail
from app.services.snapshot_run import run_snapshot


class SnapshotService:
    """
    Snapshot / Inventory 服务（v2+v3）：
    """

    @classmethod
    async def run(cls, session: AsyncSession) -> Dict[str, Any]:
        return await run_snapshot(session)

    @staticmethod
    async def query_inventory_snapshot(session: AsyncSession) -> List[Dict[str, Any]]:
        return await query_inventory_snapshot(session)

    @staticmethod
    async def query_inventory_snapshot_paged(
        session: AsyncSession,
        *,
        q: Optional[str] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> Dict[str, Any]:
        return await query_inventory_snapshot_paged(session, q=q, offset=offset, limit=limit)

    @staticmethod
    async def query_item_detail(
        session: AsyncSession,
        *,
        item_id: int,
        pools: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return await query_item_detail(session, item_id=item_id, pools=pools)
