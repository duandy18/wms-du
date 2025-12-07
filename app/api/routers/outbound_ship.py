# app/api/routers/outbound_ship.py
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.services.ship_service import ShipService

router = APIRouter(tags=["ship"])


# -------------------- /ship/calc --------------------


class ShipQuoteOut(BaseModel):
    carrier: str
    name: str
    est_cost: float
    eta: Optional[str] = None
    formula: Optional[str] = None


class ShipCalcRequest(BaseModel):
    weight_kg: float = Field(..., gt=0, description="包裹总重量（kg）")
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    debug_ref: Optional[str] = Field(None, description="调试用标记，不参与计算，仅写入日志/事件")


class ShipCalcResponse(BaseModel):
    ok: bool = True
    weight_kg: float
    dest: Optional[str] = None
    quotes: List[ShipQuoteOut]
    recommended: Optional[str] = None


@router.post("/ship/calc", response_model=ShipCalcResponse)
async def calc_shipping_quotes(
    payload: ShipCalcRequest,
    session: AsyncSession = Depends(get_session),
    current_user: Any = Depends(get_current_user),  # 只要求登录
) -> ShipCalcResponse:
    """
    计算发货费用矩阵（MVP）

    当前版本：
    - 使用 weight_kg + 省市区 计算费用
    """
    svc = ShipService(session)
    try:
        raw = await svc.calc_quotes(
            weight_kg=payload.weight_kg,
            province=payload.province,
            city=payload.city,
            district=payload.district,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    quotes = [ShipQuoteOut(**q) for q in raw.get("quotes", [])]
    return ShipCalcResponse(
        ok=raw.get("ok", True),
        weight_kg=raw["weight_kg"],
        dest=raw.get("dest"),
        quotes=quotes,
        recommended=raw.get("recommended"),
    )


# -------------------- /ship/prepare-from-order --------------------


class ShipPrepareItem(BaseModel):
    item_id: int
    qty: int


class ShipPrepareRequest(BaseModel):
    platform: str = Field(..., description="平台，例如 PDD")
    shop_id: str = Field(..., description="店铺 ID，例如 '1'")
    ext_order_no: str = Field(..., description="平台订单号")


class ShipPrepareResponse(BaseModel):
    ok: bool = True
    order_id: int
    platform: str
    shop_id: str
    ext_order_no: str
    ref: str

    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None

    # 🔹 新增：收件人完整信息
    receiver_name: Optional[str] = None
    receiver_phone: Optional[str] = None
    address_detail: Optional[str] = None

    items: List[ShipPrepareItem] = Field(default_factory=list)
    total_qty: int = 0

    # 预估总重量（kg）：基于 order_items.qty * items.weight_kg 计算
    weight_kg: Optional[float] = None

    # 订单 trace_id，用于 /ship/confirm -> lifecycle
    trace_id: Optional[str] = None


@router.post("/ship/prepare-from-order", response_model=ShipPrepareResponse)
async def prepare_from_order(
    payload: ShipPrepareRequest,
    session: AsyncSession = Depends(get_session),
    current_user: Any = Depends(get_current_user),
) -> ShipPrepareResponse:
    """
    根据平台订单信息预取发货所需基础数据：

    - order_id
    - 收货地址（省/市/区/详细地址 + 姓名/电话）
    - 行项目 item_id + qty
    - total_qty
    - weight_kg：基于 item.weight_kg 的预估总重量（不含包材）
    - trace_id：订单 trace_id（供 /ship/confirm 使用）
    """
    plat = payload.platform.upper()
    shop_id = payload.shop_id
    ext_order_no = payload.ext_order_no

    sql = text(
        """
        SELECT
          o.id AS order_id,
          o.platform,
          o.shop_id,
          o.ext_order_no,
          o.trace_id,
          addr.province,
          addr.city,
          addr.district,
          addr.receiver_name,
          addr.receiver_phone,
          addr.detail AS address_detail,
          COALESCE(SUM(COALESCE(oi.qty, 0)), 0) AS total_qty,
          COALESCE(
            SUM(
              COALESCE(oi.qty, 0) * COALESCE(it.weight_kg, 0)
            ),
            0
          ) AS estimated_weight_kg,
          COALESCE(
            json_agg(
              json_build_object(
                'item_id', oi.item_id,
                'qty', COALESCE(oi.qty, 0)
              )
            ) FILTER (WHERE oi.id IS NOT NULL),
            '[]'::json
          ) AS items
        FROM orders AS o
        LEFT JOIN order_address AS addr ON addr.order_id = o.id
        LEFT JOIN order_items AS oi ON oi.order_id = o.id
        LEFT JOIN items AS it ON it.id = oi.item_id
        WHERE o.platform = :platform
          AND o.shop_id = :shop_id
          AND o.ext_order_no = :ext_order_no
        GROUP BY
          o.id, o.platform, o.shop_id, o.ext_order_no,
          o.trace_id,
          addr.province, addr.city, addr.district,
          addr.receiver_name, addr.receiver_phone, addr.detail
        LIMIT 1
        """
    )

    row = (
        (
            await session.execute(
                sql,
                {
                    "platform": plat,
                    "shop_id": shop_id,
                    "ext_order_no": ext_order_no,
                },
            )
        )
        .mappings()
        .first()
    )

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="order not found")

    order_id = int(row["order_id"])
    province = row.get("province")
    city = row.get("city")
    district = row.get("district")
    receiver_name = row.get("receiver_name")
    receiver_phone = row.get("receiver_phone")
    address_detail = row.get("address_detail")

    total_qty = int(row["total_qty"] or 0)
    items_raw = row.get("items") or []
    items = [ShipPrepareItem(item_id=int(it["item_id"]), qty=int(it["qty"])) for it in items_raw]

    est_weight = float(row.get("estimated_weight_kg") or 0.0)
    weight_kg: Optional[float] = est_weight if est_weight > 0 else None

    trace_id = row.get("trace_id")
    ref = f"ORD:{plat}:{shop_id}:{ext_order_no}"

    return ShipPrepareResponse(
        ok=True,
        order_id=order_id,
        platform=plat,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        ref=ref,
        province=province,
        city=city,
        district=district,
        receiver_name=receiver_name,
        receiver_phone=receiver_phone,
        address_detail=address_detail,
        items=items,
        total_qty=total_qty,
        weight_kg=weight_kg,
        trace_id=trace_id,
    )


# -------------------- /ship/confirm --------------------


class ShipConfirmRequest(BaseModel):
    ref: str = Field(..., min_length=1, description="业务引用，如 ORD:PDD:1:EXT123")
    platform: str = Field(..., description="平台，如 PDD")
    shop_id: str = Field(..., description="店铺 ID，如 '1'")
    trace_id: Optional[str] = None

    # 仓库 ID（预留：后续由 Ship Cockpit 或出库链路传入）
    warehouse_id: Optional[int] = Field(None, description="发货仓库 ID（可选）")

    # 承运商信息
    carrier: Optional[str] = Field(None, description="选用的物流公司编码，例如 ZTO / JT / SF")
    carrier_name: Optional[str] = Field(None, description="物流公司名称（冗余字段）")

    # 电子面单 / 运单号
    tracking_no: Optional[str] = Field(None, description="快递运单号 / 电子面单号")

    # 重量信息
    gross_weight_kg: Optional[float] = Field(None, description="实际称重毛重（kg）")
    packaging_weight_kg: Optional[float] = Field(None, description="包材重量（kg）")

    # 费用信息
    cost_estimated: Optional[float] = Field(None, description="系统计算预估费用（元）")
    cost_real: Optional[float] = Field(None, description="月结账单对账后的实际费用（元）")

    # 时效 / 状态
    delivery_time: Optional[datetime] = Field(None, description="实际送达时间（可选）")
    status: Optional[str] = Field(None, description="IN_TRANSIT / DELIVERED / LOST / RETURNED 等")

    # 错误信息（例如面单 API 返回错误）
    error_code: Optional[str] = Field(None, description="错误码")
    error_message: Optional[str] = Field(None, description="错误信息")

    # 额外元数据（会写入审计事件 + shipping_records.meta）
    meta: Optional[Dict[str, Any]] = Field(
        None, description="附加元数据，会写入审计事件 / 发货记录表"
    )


class ShipConfirmResponse(BaseModel):
    ok: bool = True
    ref: str
    trace_id: Optional[str] = None


@router.post("/ship/confirm", response_model=ShipConfirmResponse)
async def confirm_ship(
    payload: ShipConfirmRequest,
    session: AsyncSession = Depends(get_session),
    current_user: Any = Depends(get_current_user),
) -> ShipConfirmResponse:
    """
    记录一次发货完成事件（Phase 2）

    - 不做库存扣减（库存扣减已由 Outbound/Pick 链路完成）
    - 写审计事件（OUTBOUND / SHIP_COMMIT），供 Trace / Lifecycle 使用
    - 写 shipping_records（发货账本），用于后续对账 / KPI / 成本分析
    """
    svc = ShipService(session)

    # 审计事件 meta：带上尽可能多的结构化字段
    meta: Dict[str, Any] = {}
    if payload.meta:
        meta.update(payload.meta)

    if payload.carrier:
        meta["carrier"] = payload.carrier
    if payload.carrier_name:
        meta["carrier_name"] = payload.carrier_name
    if payload.tracking_no:
        meta["tracking_no"] = payload.tracking_no

    if payload.gross_weight_kg is not None:
        meta["gross_weight_kg"] = payload.gross_weight_kg
    if payload.packaging_weight_kg is not None:
        meta["packaging_weight_kg"] = payload.packaging_weight_kg

    if payload.cost_estimated is not None:
        meta["cost_estimated"] = payload.cost_estimated
    if payload.cost_real is not None:
        meta["cost_real"] = payload.cost_real

    if payload.status:
        meta["status"] = payload.status
    if payload.error_code:
        meta["error_code"] = payload.error_code
    if payload.error_message:
        meta["error_message"] = payload.error_message
    if payload.delivery_time:
        meta["delivery_time"] = payload.delivery_time.isoformat()

    if payload.warehouse_id is not None:
        meta["warehouse_id"] = payload.warehouse_id

    # Step 1: 写审计事件
    data = await svc.commit(
        ref=payload.ref,
        platform=payload.platform,
        shop_id=payload.shop_id,
        trace_id=payload.trace_id,
        meta=meta or None,
    )

    # 把 meta 转成 JSON 字符串，避免 asyncpg jsonb encoder 报错
    json_meta: Optional[str]
    if meta:
        json_meta = json.dumps(meta, ensure_ascii=False)
    else:
        json_meta = None

    # Step 2: 写 shipping_records
    insert_sql = text(
        """
        INSERT INTO shipping_records (
            order_ref,
            platform,
            shop_id,
            carrier_code,
            carrier_name,
            tracking_no,
            trace_id,
            warehouse_id,
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
            :carrier_code,
            :carrier_name,
            :tracking_no,
            :trace_id,
            :warehouse_id,
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
            "order_ref": payload.ref,
            "platform": payload.platform.upper(),
            "shop_id": payload.shop_id,
            "carrier_code": payload.carrier,
            "carrier_name": payload.carrier_name,
            "tracking_no": payload.tracking_no,
            "trace_id": payload.trace_id,
            "warehouse_id": payload.warehouse_id,
            "weight_kg": None,  # 未来可以存“净重估算”
            "gross_weight_kg": payload.gross_weight_kg,
            "packaging_weight_kg": payload.packaging_weight_kg,
            "cost_estimated": payload.cost_estimated,
            "cost_real": payload.cost_real,
            "delivery_time": payload.delivery_time,
            "status": payload.status or "IN_TRANSIT",
            "error_code": payload.error_code,
            "error_message": payload.error_message,
            "meta": json_meta,
        },
    )

    await session.commit()

    return ShipConfirmResponse(
        ok=data.get("ok", True),
        ref=payload.ref,
        trace_id=payload.trace_id,
    )
