# app/api/routers/channel_inventory_routes.py
from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Depends, Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.services.channel_inventory_service import ChannelInventoryService

from app.api.routers.channel_inventory_mappers import map_multi, map_single
from app.api.routers.channel_inventory_schemas import (
    ChannelInventoryModel,
    ChannelInventoryMultiModel,
)


def register(router: APIRouter) -> None:
    @router.get(
        "/{platform}/{shop_id}/{warehouse_id:int}/{item_id:int}",
        response_model=ChannelInventoryModel,
    )
    async def get_channel_inventory_single(
        platform: str = Path(..., description="平台标识，如 PDD / TB / JD"),
        shop_id: str = Path(..., description="平台侧店铺 ID"),
        warehouse_id: int = Path(..., description="内部 warehouse_id"),
        item_id: int = Path(..., description="内部 item_id"),
        session: AsyncSession = Depends(get_session),
    ) -> ChannelInventoryModel:
        svc = ChannelInventoryService(session)
        ci = await svc.get_single_item(
            platform=platform,
            shop_id=shop_id,
            warehouse_id=warehouse_id,
            item_id=item_id,
        )
        return map_single(ci)

    @router.get(
        "/{platform}/{shop_id}/item/{item_id:int}",
        response_model=ChannelInventoryMultiModel,
    )
    async def get_channel_inventory_multi(
        platform: str = Path(..., description="平台标识，如 PDD / TB / JD"),
        shop_id: str = Path(..., description="平台侧店铺 ID"),
        item_id: int = Path(..., description="内部 item_id"),
        session: AsyncSession = Depends(get_session),
    ) -> ChannelInventoryMultiModel:
        svc = ChannelInventoryService(session)

        rows = await session.execute(
            text(
                """
                SELECT
                    sw.warehouse_id,
                    sw.is_top,
                    sw.is_default,
                    sw.priority
                  FROM store_warehouse AS sw
                  JOIN stores AS s
                    ON sw.store_id = s.id
                 WHERE s.platform = :p
                   AND s.shop_id  = :s
                   AND s.active   = TRUE
                 ORDER BY sw.is_top DESC,
                          sw.priority ASC,
                          sw.warehouse_id ASC
                """
            ),
            {"p": platform.upper(), "s": shop_id},
        )
        bindings = rows.fetchall()

        bindings_by_wh: Dict[int, Dict[str, object]] = {}
        if bindings:
            for wh_id, is_top, is_default, priority in bindings:
                wid = int(wh_id)
                bindings_by_wh[wid] = {
                    "is_top": bool(is_top),
                    "is_default": bool(is_default),
                    "priority": int(priority or 100),
                }
            cis = await svc.get_multi_item_for_store(
                platform=platform,
                shop_id=shop_id,
                item_id=item_id,
            )
            return map_multi(
                platform=platform,
                shop_id=shop_id,
                item_id=item_id,
                lst=cis,
                bindings_by_wh=bindings_by_wh,
            )

        cis = await svc.get_multi_item(
            platform=platform,
            shop_id=shop_id,
            item_id=item_id,
        )
        return map_multi(
            platform=platform,
            shop_id=shop_id,
            item_id=item_id,
            lst=cis,
            bindings_by_wh=None,
        )
