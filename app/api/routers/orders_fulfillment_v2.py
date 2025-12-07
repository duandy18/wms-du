# app/api/routers/orders_fulfillment_v2.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, conint, constr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.services.order_event_bus import OrderEventBus
from app.services.order_service import OrderService
from app.services.pick_service import PickService
from app.services.ship_service import ShipService
from app.services.soft_reserve_service import SoftReserveService
from app.services.waybill_service import WaybillRequest, WaybillService

router = APIRouter(prefix="/orders", tags=["orders-fulfillment-v2"])


# ---------------------------------------------------------------------------
# 工具：从 URL 解析订单上下文，并获取订单 ref + trace_id
# ---------------------------------------------------------------------------


async def _get_order_ref_and_trace_id(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ext_order_no: str,
) -> Tuple[str, Optional[str]]:
    """
    统一解析订单 ref + trace_id：

    - ref 固定为 ORD:{PLAT}:{shop_id}:{ext_order_no}
    - trace_id 优先通过 OrderService.get_trace_id_for_order 获取
    - 若失败 / 返回 None，则直接到 orders 表兜底查 trace_id
    """
    plat = platform.upper()
    order_ref = f"ORD:{plat}:{shop_id}:{ext_order_no}"

    trace_id: Optional[str] = None

    # 1) 首选：通过服务层按 ref 查 trace_id（兼容已有实现）
    try:
        trace_id = await OrderService.get_trace_id_for_order(
            session=session,
            platform=plat,
            shop_id=shop_id,
            ref=order_ref,
        )
    except Exception:
        trace_id = None

    # 2) 兜底：直接从 orders 表读取 trace_id
    if not trace_id:
        row = (
            (
                await session.execute(
                    text(
                        """
                    SELECT trace_id
                      FROM orders
                     WHERE platform = :p
                       AND shop_id  = :s
                       AND ext_order_no = :o
                     ORDER BY id DESC
                     LIMIT 1
                    """
                    ),
                    {"p": plat, "s": shop_id, "o": ext_order_no},
                )
            )
            .mappings()
            .first()
        )
        if row:
            trace_id = row.get("trace_id")

    return order_ref, trace_id


# ---------------------------------------------------------------------------
# 1) 订单预占 v2
# ---------------------------------------------------------------------------


class ReserveLineIn(BaseModel):
    item_id: conint(gt=0)
    qty: conint(gt=0)


class ReserveRequest(BaseModel):
    lines: List[ReserveLineIn] = Field(default_factory=list)


class ReserveResponse(BaseModel):
    status: str
    ref: str
    reservation_id: Optional[int] = None
    lines: int


@router.post(
    "/{platform}/{shop_id}/{ext_order_no}/reserve",
    response_model=ReserveResponse,
)
async def order_reserve(
    platform: str,
    shop_id: str,
    ext_order_no: str,
    body: ReserveRequest,
    session: AsyncSession = Depends(get_session),
):
    plat = platform.upper()

    if not body.lines:
        return ReserveResponse(
            status="OK",
            ref=f"ORD:{plat}:{shop_id}:{ext_order_no}",
            reservation_id=None,
            lines=0,
        )

    order_ref, trace_id = await _get_order_ref_and_trace_id(
        session=session,
        platform=plat,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
    )

    try:
        result = await OrderService.reserve(
            session,
            platform=plat,
            shop_id=shop_id,
            ref=order_ref,
            lines=[{"item_id": line.item_id, "qty": line.qty} for line in body.lines],
            trace_id=trace_id,
        )
        await session.commit()
    except ValueError as e:
        await session.rollback()
        raise HTTPException(409, detail=str(e))
    except Exception:
        await session.rollback()
        raise

    return ReserveResponse(
        status=result.get("status", "OK"),
        ref=result.get("ref", order_ref),
        reservation_id=result.get("reservation_id"),
        lines=result.get("lines", len(body.lines)),
    )


# ---------------------------------------------------------------------------
# 2) 订单拣货 v2（扣库 + 自动消耗预占）
# ---------------------------------------------------------------------------


class PickLineIn(BaseModel):
    item_id: conint(gt=0)
    qty: conint(gt=0)


class PickRequest(BaseModel):
    warehouse_id: conint(gt=0) = Field(
        ...,
        description="拣货仓库 ID（>0，允许 1）",
    )
    batch_code: constr(min_length=1)
    lines: List[PickLineIn] = Field(default_factory=list)
    occurred_at: Optional[datetime] = Field(
        default=None,
        description="拣货时间（缺省为当前 UTC 时间）",
    )


class PickResponse(BaseModel):
    item_id: int
    warehouse_id: int
    batch_code: str
    picked: int
    stock_after: Optional[int] = None
    ref: str
    status: str


@router.post(
    "/{platform}/{shop_id}/{ext_order_no}/pick",
    response_model=List[PickResponse],
)
async def order_pick(
    platform: str,
    shop_id: str,
    ext_order_no: str,
    body: PickRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    订单拣货 v2：

    - 调用 PickService.record_pick 扣减库存（ledger: PICK）
    - 紧接着调用 SoftReserveService.pick_consume：
        * 将该订单 ref 对应的 reservation_lines.consumed_qty 补齐
        * 形成「预占创建 → 预占消耗」完整闭环
    """
    plat = platform.upper()

    if not body.lines:
        return []

    order_ref, trace_id = await _get_order_ref_and_trace_id(
        session=session,
        platform=plat,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
    )

    svc = PickService()
    soft_reserve = SoftReserveService()
    occurred_at = body.occurred_at or datetime.now(timezone.utc)

    responses: List[PickResponse] = []
    ref_line = 1

    try:
        # 1) 扣库（PICK）
        for line in body.lines:
            result = await svc.record_pick(
                session=session,
                item_id=line.item_id,
                qty=line.qty,
                ref=order_ref,
                occurred_at=occurred_at,
                batch_code=body.batch_code,
                warehouse_id=body.warehouse_id,
                trace_id=trace_id,
                start_ref_line=ref_line,
            )
            ref_line = result.get("ref_line", ref_line) + 1

            responses.append(
                PickResponse(
                    item_id=line.item_id,
                    warehouse_id=result.get("warehouse_id", body.warehouse_id),
                    batch_code=result.get("batch_code", body.batch_code),
                    picked=result.get("picked", line.qty),
                    stock_after=result.get("stock_after"),
                    ref=result.get("ref", order_ref),
                    status=result.get("status", "OK"),
                )
            )

        # 2) 自动消耗预占（reservation_lines.consumed_qty）
        await soft_reserve.pick_consume(
            session=session,
            platform=plat,
            shop_id=shop_id,
            warehouse_id=body.warehouse_id,
            ref=order_ref,
            occurred_at=occurred_at,
            trace_id=trace_id,
        )

        await session.commit()

    except ValueError as e:
        await session.rollback()
        raise HTTPException(409, detail=str(e))
    except Exception:
        await session.rollback()
        raise

    return responses


# ---------------------------------------------------------------------------
# 3) 订单发运 v2（只写审计，不写账本）
# ---------------------------------------------------------------------------


class ShipLineIn(BaseModel):
    item_id: conint(gt=0)
    qty: conint(gt=0)


class ShipRequest(BaseModel):
    warehouse_id: conint(gt=0)
    lines: List[ShipLineIn] = Field(default_factory=list)
    occurred_at: Optional[datetime] = Field(
        default=None,
        description="发运时间（缺省为当前 UTC 时间）",
    )


class ShipResponse(BaseModel):
    status: str
    ref: str
    event: str = "SHIP_COMMIT"


@router.post(
    "/{platform}/{shop_id}/{ext_order_no}/ship",
    response_model=ShipResponse,
)
async def order_ship(
    platform: str,
    shop_id: str,
    ext_order_no: str,
    body: ShipRequest,
    session: AsyncSession = Depends(get_session),
):
    plat = platform.upper()

    order_ref, trace_id = await _get_order_ref_and_trace_id(
        session=session,
        platform=plat,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
    )

    svc = ShipService(session=session)
    occurred_at = body.occurred_at or datetime.now(timezone.utc)

    lines_meta = [{"item_id": line.item_id, "qty": line.qty} for line in body.lines]
    meta = {
        "platform": plat,
        "shop_id": shop_id,
        "warehouse_id": int(body.warehouse_id),
        "occurred_at": occurred_at.isoformat(),
        "lines": lines_meta,
    }

    try:
        # 写发运审计（OUTBOUND/SHIP_COMMIT）
        result = await svc.commit(
            ref=order_ref,
            platform=plat,
            shop_id=shop_id,
            trace_id=trace_id,
            meta=meta,
        )

        # 订单 status：SHIPPED（当前实现按“整单发完”口径）
        try:
            await session.execute(
                text(
                    """
                    UPDATE orders
                       SET status = :st,
                           updated_at = NOW()
                     WHERE platform = :p
                       AND shop_id  = :s
                       AND ext_order_no = :o
                    """
                ),
                {
                    "st": "SHIPPED",
                    "p": plat,
                    "s": shop_id,
                    "o": ext_order_no,
                },
            )
        except Exception:
            pass

        # 追加订单事件：ORDER_SHIPPED（flow=ORDER）
        try:
            await OrderEventBus.order_shipped(
                session,
                ref=order_ref,
                platform=plat,
                shop_id=shop_id,
                warehouse_id=int(body.warehouse_id),
                lines=lines_meta,
                occurred_at=occurred_at,
                trace_id=trace_id,
            )
        except Exception:
            pass

        await session.commit()
    except Exception:
        await session.rollback()
        raise

    return ShipResponse(
        status="OK" if result.get("ok") else "ERROR",
        ref=order_ref,
        event="SHIP_COMMIT",
    )


# ---------------------------------------------------------------------------
# 4) 订单发运 v2 + 平台出单（Waybill，模式 2）
# ---------------------------------------------------------------------------


class ShipWithWaybillRequest(BaseModel):
    warehouse_id: conint(gt=0) = Field(..., description="发货仓库 ID")
    carrier_code: constr(min_length=1) = Field(..., description="快递公司编码，例如 ZTO / JT / SF")
    carrier_name: Optional[str] = Field(None, description="快递公司名称（冗余字段）")
    weight_kg: float = Field(..., gt=0, description="包裹毛重（kg）")

    # 收件人信息（从订单地址来，当前可选）
    receiver_name: Optional[str] = None
    receiver_phone: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    address_detail: Optional[str] = None


class ShipWithWaybillResponse(BaseModel):
    ok: bool
    ref: str
    tracking_no: str
    carrier_code: str
    carrier_name: Optional[str] = None
    status: str = "IN_TRANSIT"
    label_base64: Optional[str] = None
    label_format: Optional[str] = None


@router.post(
    "/{platform}/{shop_id}/{ext_order_no}/ship-with-waybill",
    response_model=ShipWithWaybillResponse,
)
async def order_ship_with_waybill(
    platform: str,
    shop_id: str,
    ext_order_no: str,
    body: ShipWithWaybillRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    模式 2：由 WMS 选快递公司 → 调平台接口获取单号（当前 Fake）→ 写发货账本。

    当前版本：
      - 用 WaybillService(Fake) 生成 tracking_no = {carrier_code}-{ext_order_no}
      - 调 ShipService.commit 写发货审计事件
      - 直接 INSERT 一条 shipping_records（IN_TRANSIT）
    """
    plat = platform.upper()

    # 1) 解析订单 ref + trace_id
    order_ref, trace_id = await _get_order_ref_and_trace_id(
        session=session,
        platform=plat,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
    )

    waybill_svc = WaybillService()
    wb_req = WaybillRequest(
        provider_code=body.carrier_code,
        platform=plat,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        receiver={
            "name": body.receiver_name,
            "phone": body.receiver_phone,
            "province": body.province,
            "city": body.city,
            "district": body.district,
            "detail": body.address_detail,
        },
        cargo={"weight_kg": float(body.weight_kg or 0.0)},
        extras={},
    )
    wb_result = await waybill_svc.request_waybill(wb_req)
    if not wb_result.ok or not wb_result.tracking_no:
        raise HTTPException(
            status_code=502,
            detail=f"waybill request failed: {wb_result.error_code or ''} {wb_result.error_message or ''}",
        )

    tracking_no = wb_result.tracking_no

    # 2) 写发运审计（OUTBOUND / SHIP_COMMIT）
    svc = ShipService(session=session)
    occurred_at = datetime.now(timezone.utc)
    meta = {
        "platform": plat,
        "shop_id": shop_id,
        "warehouse_id": int(body.warehouse_id),
        "occurred_at": occurred_at.isoformat(),
        "carrier_code": body.carrier_code,
        "carrier_name": body.carrier_name,
        "tracking_no": tracking_no,
        "weight_kg": float(body.weight_kg or 0.0),
        "receiver": {
            "name": body.receiver_name,
            "phone": body.receiver_phone,
            "province": body.province,
            "city": body.city,
            "district": body.district,
            "detail": body.address_detail,
        },
        "waybill_source": "PLATFORM_FAKE",
    }

    try:
        audit_res = await svc.commit(
            ref=order_ref,
            platform=plat,
            shop_id=shop_id,
            trace_id=trace_id,
            meta=meta,
        )
    except Exception:
        await session.rollback()
        raise

    # 3) 写 shipping_records（IN_TRANSIT）
    json_meta: Optional[str] = json.dumps(meta, ensure_ascii=False) if meta else None

    insert_sql = text(
        """
        INSERT INTO shipping_records (
            order_ref,
            platform,
            shop_id,
            warehouse_id,
            carrier_code,
            carrier_name,
            tracking_no,
            trace_id,
            weight_kg,
            gross_weight_kg,
            packaging_weight_kg,
            cost_estimated,
            cost_real,
            delivery_time,
            status,
            error_code,
            error_message,
            meta
        )
        VALUES (
            :order_ref,
            :platform,
            :shop_id,
            :warehouse_id,
            :carrier_code,
            :carrier_name,
            :tracking_no,
            :trace_id,
            :weight_kg,
            :gross_weight_kg,
            :packaging_weight_kg,
            :cost_estimated,
            :cost_real,
            :delivery_time,
            :status,
            :error_code,
            :error_message,
            :meta
        )
        """
    )

    await session.execute(
        insert_sql,
        {
            "order_ref": order_ref,
            "platform": plat,
            "shop_id": shop_id,
            "warehouse_id": int(body.warehouse_id),
            "carrier_code": body.carrier_code,
            "carrier_name": body.carrier_name,
            "tracking_no": tracking_no,
            "trace_id": trace_id,
            "weight_kg": None,  # 未来可以区分净重/毛重
            "gross_weight_kg": float(body.weight_kg or 0.0),
            "packaging_weight_kg": None,
            "cost_estimated": None,
            "cost_real": None,
            "delivery_time": None,
            "status": "IN_TRANSIT",
            "error_code": None,
            "error_message": None,
            "meta": json_meta,
        },
    )

    await session.commit()

    return ShipWithWaybillResponse(
        ok=audit_res.get("ok", True),
        ref=order_ref,
        tracking_no=tracking_no,
        carrier_code=body.carrier_code,
        carrier_name=body.carrier_name,
        status="IN_TRANSIT",
        label_base64=None,
        label_format=None,
    )
