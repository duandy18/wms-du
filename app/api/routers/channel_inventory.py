from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.services.channel_inventory_service import ChannelInventory, ChannelInventoryService

router = APIRouter(prefix="/channel-inventory", tags=["channel-inventory"])


class BatchQtyModel(BaseModel):
    batch_code: str = Field(..., description="批次编码（包装上的批号）")
    qty: int = Field(..., description="该批次在此仓的实时库存数量")


class ChannelInventoryModel(BaseModel):
    platform: str
    shop_id: str
    warehouse_id: int
    item_id: int

    on_hand: int = Field(..., description="该仓该货品的实时库存合计（所有批次）")
    reserved_open: int = Field(..., description="该平台/店铺/仓下 open reservations 锁量")
    available: int = Field(..., description="可售量 = max(on_hand - reserved_open, 0)")

    batches: List[BatchQtyModel] = Field(
        default_factory=list,
        description="按批次的库存明细（仅供人工参考，不影响 available 口径）",
    )


class WarehouseInventoryModel(BaseModel):
    warehouse_id: int
    on_hand: int
    reserved_open: int
    available: int
    batches: List[BatchQtyModel] = Field(default_factory=list)

    is_top: bool = Field(False, description="是否主仓（store_warehouse.is_top）")
    is_default: bool = Field(False, description="是否默认仓（历史字段）")
    priority: int = Field(100, description="路由优先级（数字越小越优先）")


class ChannelInventoryMultiModel(BaseModel):
    platform: str
    shop_id: str
    item_id: int
    warehouses: List[WarehouseInventoryModel] = Field(
        default_factory=list, description="各仓的库存与锁量明细"
    )


def _map_single(ci: ChannelInventory) -> ChannelInventoryModel:
    return ChannelInventoryModel(
        platform=ci.platform,
        shop_id=ci.shop_id,
        warehouse_id=ci.warehouse_id,
        item_id=ci.item_id,
        on_hand=ci.on_hand,
        reserved_open=ci.reserved_open,
        available=ci.available,
        batches=[BatchQtyModel(batch_code=b.batch_code, qty=b.qty) for b in ci.batches],
    )


def _map_multi(
    platform: str,
    shop_id: str,
    item_id: int,
    lst: List[ChannelInventory],
    bindings_by_wh: Optional[Dict[int, Dict[str, object]]] = None,
) -> ChannelInventoryMultiModel:
    warehouses: List[WarehouseInventoryModel] = []

    for ci in lst:
        meta = bindings_by_wh.get(ci.warehouse_id) if bindings_by_wh else None
        warehouses.append(
            WarehouseInventoryModel(
                warehouse_id=ci.warehouse_id,
                on_hand=ci.on_hand,
                reserved_open=ci.reserved_open,
                available=ci.available,
                batches=[BatchQtyModel(batch_code=b.batch_code, qty=b.qty) for b in ci.batches],
                is_top=bool(meta.get("is_top")) if meta else False,
                is_default=bool(meta.get("is_default")) if meta else False,
                priority=(
                    int(meta.get("priority")) if meta and meta.get("priority") is not None else 100
                ),
            )
        )

    return ChannelInventoryMultiModel(
        platform=platform,
        shop_id=shop_id,
        item_id=item_id,
        warehouses=warehouses,
    )


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
    return _map_single(ci)


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
        return _map_multi(
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
    return _map_multi(
        platform=platform,
        shop_id=shop_id,
        item_id=item_id,
        lst=cis,
        bindings_by_wh=None,
    )
