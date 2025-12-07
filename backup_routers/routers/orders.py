# app/routers/orders.py
from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, conlist, PositiveInt
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["orders"])


# ---------- 依赖解析（与 admin_snapshot 相同的三段兜底策略） ----------
try:
    from app.deps import get_async_session as _get_session  # type: ignore
except Exception:  # noqa: BLE001
    try:
        from app.db import get_async_session as _get_session  # type: ignore
    except Exception:  # noqa: BLE001

        async def _get_session(request: Request) -> AsyncSession:  # type: ignore[override]
            maker = getattr(request.app.state, "async_sessionmaker", None)
            if maker is None:
                raise RuntimeError(
                    "No async sessionmaker available. "
                    "Provide app.deps.get_async_session / app.db.get_async_session "
                    "or set app.state.async_sessionmaker in app.main."
                )
            async with maker() as session:  # type: ignore[func-returns-value]
                yield session


# ---------- 请求 / 响应模型 ----------
class ReserveLine(BaseModel):
    item_id: PositiveInt
    qty: PositiveInt = Field(..., description="下单占用数量")


class ShipLine(BaseModel):
    item_id: PositiveInt
    location_id: PositiveInt
    qty: PositiveInt = Field(..., description="出库数量")


class ReserveReq(BaseModel):
    platform: str = Field("pdd", description="平台标识")
    shop_id: str = Field(..., description="店铺唯一标识（你当前模型用 Store.name ）")
    ref: str = Field(..., description="幂等键，如订单号/波次号")
    lines: conlist(ReserveLine, min_items=1)


class CancelReq(ReserveReq):
    pass


class ShipReq(BaseModel):
    platform: str = Field("pdd", description="平台标识")
    shop_id: str = Field(..., description="店铺唯一标识")
    ref: str = Field(..., description="幂等键，如发货单号/波次号")
    lines: conlist(ShipLine, min_items=1)
    refresh_visible: bool = True
    warehouse_id: Optional[int] = Field(None, description="预留（v1.2 多仓启用）")


class PreviewReq(BaseModel):
    platform: str = Field("pdd", description="平台标识")
    shop_id: str = Field(..., description="店铺唯一标识")
    item_ids: conlist(PositiveInt, min_items=1)
    warehouse_id: Optional[int] = None


# ---------- 路由 ----------
@router.post("/reserve")
async def orders_reserve(payload: ReserveReq, session: AsyncSession = Depends(_get_session)):
    out = await OrderService.reserve(
        session,
        platform=payload.platform,
        shop_id=payload.shop_id,
        ref=payload.ref,
        lines=[l.model_dump() for l in payload.lines],
    )
    out["received_at"] = datetime.now(UTC).isoformat()
    return out


@router.post("/cancel")
async def orders_cancel(payload: CancelReq, session: AsyncSession = Depends(_get_session)):
    out = await OrderService.cancel(
        session,
        platform=payload.platform,
        shop_id=payload.shop_id,
        ref=payload.ref,
        lines=[l.model_dump() for l in payload.lines],
    )
    out["received_at"] = datetime.now(UTC).isoformat()
    return out


@router.post("/ship")
async def orders_ship(payload: ShipReq, session: AsyncSession = Depends(_get_session)):
    out = await OrderService.ship(
        session,
        platform=payload.platform,
        shop_id=payload.shop_id,
        ref=payload.ref,
        lines=[l.model_dump() for l in payload.lines],
        refresh_visible=payload.refresh_visible,
        warehouse_id=payload.warehouse_id,
    )
    out["received_at"] = datetime.now(UTC).isoformat()
    return out


@router.post("/preview-visible")
async def orders_preview_visible(
    payload: PreviewReq, session: AsyncSession = Depends(_get_session)
):
    out = await OrderService.preview_visible(
        session,
        platform=payload.platform,
        shop_id=payload.shop_id,
        item_ids=list(payload.item_ids),
        warehouse_id=payload.warehouse_id,
    )
    out["received_at"] = datetime.now(UTC).isoformat()
    return out
