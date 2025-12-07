# app/api/routers/devconsole_orders.py
from __future__ import annotations

import random
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.models.enums import MovementType
from app.services.dev_orders_service import DevOrdersService
from app.services.order_reconcile_service import OrderReconcileService
from app.services.order_service import OrderService
from app.services.stock_service import StockService
from app.services.store_service import StoreService

# ⭐ router 必须在最上方定义
router = APIRouter(
    prefix="/dev/orders",
    tags=["devconsole-orders"],
)

# ------------------------- Pydantic 模型 ------------------------- #


class DevOrderInfo(BaseModel):
    id: int
    platform: str
    shop_id: str
    ext_order_no: str
    status: Optional[str] = None
    trace_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    warehouse_id: Optional[int] = None
    order_amount: Optional[float] = None
    pay_amount: Optional[float] = None


class DevOrderView(BaseModel):
    order: DevOrderInfo
    trace_id: Optional[str] = Field(
        None,
        description="订单关联 trace_id，可直接跳转生命周期/trace 页面",
    )


class DevOrderItemFact(BaseModel):
    item_id: int
    sku_id: Optional[str] = None
    title: Optional[str] = None
    qty_ordered: int
    qty_shipped: int
    qty_returned: int
    qty_remaining_refundable: int


class DevOrderFacts(BaseModel):
    order: DevOrderInfo
    items: List[DevOrderItemFact] = Field(default_factory=list)


class DevOrderSummary(BaseModel):
    id: int
    platform: str
    shop_id: str
    ext_order_no: str
    status: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    warehouse_id: Optional[int] = None
    order_amount: Optional[float] = None
    pay_amount: Optional[float] = None


class DevOrderReconcileLine(BaseModel):
    item_id: int
    sku_id: Optional[str] = None
    title: Optional[str] = None
    qty_ordered: int
    qty_shipped: int
    qty_returned: int
    remaining_refundable: int


class DevOrderReconcileResultModel(BaseModel):
    order_id: int
    platform: str
    shop_id: str
    ext_order_no: str
    issues: List[str] = Field(default_factory=list)
    lines: List[DevOrderReconcileLine] = Field(default_factory=list)


class DevReconcileRangeResult(BaseModel):
    count: int
    order_ids: List[int] = Field(default_factory=list)


class DevDemoOrderOut(BaseModel):
    order_id: int
    platform: str
    shop_id: str
    ext_order_no: str
    trace_id: Optional[str] = None


class DevEnsureWarehouseOut(BaseModel):
    ok: bool
    order_id: int
    platform: str
    shop_id: str
    ext_order_no: str
    store_id: Optional[int] = None
    warehouse_id: Optional[int] = None
    source: str
    message: Optional[str] = None


# ------------------------- 路由：生成 demo 订单 ------------------------- #


@router.post("/demo", response_model=DevDemoOrderOut)
async def create_demo_order(
    platform: str = Query("PDD"),
    shop_id: str = Query("1"),
    session: AsyncSession = Depends(get_session),
) -> DevDemoOrderOut:
    """
    生成 demo 订单（修复 trace/ref 误判 lifecycle 的最终版本）
    """

    # 1) 随机物品
    rows = (
        await session.execute(
            text(
                """
                SELECT id FROM items ORDER BY id LIMIT 10
                """
            )
        )
    ).fetchall()
    item_ids = [int(r[0]) for r in rows]
    if not item_ids:
        raise HTTPException(400, "items 表为空，请先添加商品。")

    # 仓库
    wh_row = (
        (await session.execute(text("SELECT id FROM warehouses ORDER BY id LIMIT 1")))
        .mappings()
        .first()
    )
    if not wh_row:
        raise HTTPException(400, "warehouses 表为空，请创建至少一个仓库。")
    warehouse_id = int(wh_row["id"])

    now = datetime.now(timezone.utc)
    plat = platform.upper()
    shop = shop_id.strip()

    # ext_order_no
    uid = uuid.uuid4().hex[:6]
    ext_order_no = f"DEMO2-{now:%Y%m%d}-{uid}"

    # trace_id（完全隔离，不会与订单 trace 相似）
    trace_uid = uuid.uuid4().hex[:8]
    trace_id = f"demo-order-trace:{plat}:{shop}:{ext_order_no}:{trace_uid}"

    # 组装 items
    k = random.randint(1, min(3, len(item_ids)))
    chosen = random.sample(item_ids, k=k)
    items = []
    total = Decimal("0.00")
    order_lines = []

    for idx, item_id in enumerate(chosen, start=1):
        qty = random.randint(1, 3)
        price = Decimal("10.00") * idx
        total += price * qty
        items.append({"item_id": item_id, "qty": qty, "price": float(price)})
        order_lines.append((item_id, qty))

    # 2) 落订单
    result = await OrderService.ingest(
        session=session,
        platform=plat,
        shop_id=shop,
        ext_order_no=ext_order_no,
        occurred_at=now,
        order_amount=total,
        pay_amount=total,
        items=items,
        address=None,
        extras=None,
        trace_id=trace_id,
    )
    order_id = int(result["id"])

    # 3) 绑定仓库
    await session.execute(
        text("UPDATE orders SET warehouse_id=:wid WHERE id=:oid"),
        {"wid": warehouse_id, "oid": order_id},
    )

    # 4) seed 库存（完全隔离 trace/ref）
    stock_service = StockService()
    prod = date.today()
    exp = prod + timedelta(days=365)

    seed_uid = uuid.uuid4().hex[:6]
    seed_trace_id = f"demo-seed-trace:{order_id}:{seed_uid}"
    batch_code = "AUTO"

    for idx, (item_id, qty) in enumerate(order_lines, start=1):
        seed_qty = max(20, qty * 10)
        seed_ref = f"demo-seed-ref:{order_id}:{seed_uid}:{idx}"

        await stock_service.adjust(
            session=session,
            item_id=item_id,
            warehouse_id=warehouse_id,
            delta=seed_qty,
            reason=MovementType.RECEIPT,
            ref=seed_ref,  # ❗ 不再使用 demo:order:* 避免 lifecycle fallback
            ref_line=idx,
            occurred_at=now,
            batch_code=batch_code,
            production_date=prod,
            expiry_date=exp,
            trace_id=seed_trace_id,
        )

    await session.commit()

    return DevDemoOrderOut(
        order_id=order_id,
        platform=plat,
        shop_id=shop,
        ext_order_no=ext_order_no,
        trace_id=trace_id,
    )


# ------------------------- 单订单头部 ------------------------- #


@router.get("/{platform}/{shop_id}/{ext_order_no}", response_model=DevOrderView)
async def get_dev_order_view(
    platform: str,
    shop_id: str,
    ext_order_no: str,
    session: AsyncSession = Depends(get_session),
) -> DevOrderView:
    svc = DevOrdersService(session)
    head = await svc.get_order_head(platform, shop_id, ext_order_no)

    if head is None:
        raise HTTPException(404, "order not found")

    order = DevOrderInfo(
        id=head["id"],
        platform=head["platform"],
        shop_id=head["shop_id"],
        ext_order_no=head["ext_order_no"],
        status=head.get("status"),
        trace_id=head.get("trace_id"),
        created_at=head["created_at"],
        updated_at=head.get("updated_at"),
        warehouse_id=head.get("warehouse_id"),
        order_amount=float(head["order_amount"]) if head.get("order_amount") else None,
        pay_amount=float(head["pay_amount"]) if head.get("pay_amount") else None,
    )

    return DevOrderView(order=order, trace_id=order.trace_id)


# ------------------------- facts ------------------------- #


@router.get("/{platform}/{shop_id}/{ext_order_no}/facts", response_model=DevOrderFacts)
async def get_dev_order_facts(
    platform: str,
    shop_id: str,
    ext_order_no: str,
    session: AsyncSession = Depends(get_session),
) -> DevOrderFacts:
    svc = DevOrdersService(session)
    head, items = await svc.get_order_facts(platform, shop_id, ext_order_no)

    order = DevOrderInfo(
        id=head["id"],
        platform=head["platform"],
        shop_id=head["shop_id"],
        ext_order_no=head["ext_order_no"],
        status=head.get("status"),
        trace_id=head.get("trace_id"),
        created_at=head["created_at"],
        updated_at=head.get("updated_at"),
        warehouse_id=head.get("warehouse_id"),
        order_amount=float(head["order_amount"]) if head.get("order_amount") else None,
        pay_amount=float(head["pay_amount"]) if head.get("pay_amount") else None,
    )

    facts = [
        DevOrderItemFact(
            item_id=it["item_id"],
            sku_id=it.get("sku_id"),
            title=it.get("title"),
            qty_ordered=it["qty_ordered"],
            qty_shipped=it["qty_shipped"],
            qty_returned=it["qty_returned"],
            qty_remaining_refundable=it["qty_remaining_refundable"],
        )
        for it in items
    ]

    return DevOrderFacts(order=order, items=facts)


# ------------------------- 对账 ------------------------- #


@router.get("/by-id/{order_id}/reconcile", response_model=DevOrderReconcileResultModel)
async def reconcile_order_by_id(
    order_id: int,
    session: AsyncSession = Depends(get_session),
) -> DevOrderReconcileResultModel:
    svc = OrderReconcileService(session)
    res = await svc.reconcile_order(order_id)

    lines = [
        DevOrderReconcileLine(
            item_id=lf.item_id,
            sku_id=lf.sku_id,
            title=lf.title,
            qty_ordered=lf.qty_ordered,
            qty_shipped=lf.qty_shipped,
            qty_returned=lf.qty_returned,
            remaining_refundable=lf.remaining_refundable,
        )
        for lf in res.lines
    ]

    return DevOrderReconcileResultModel(
        order_id=res.order_id,
        platform=res.platform,
        shop_id=res.shop_id,
        ext_order_no=res.ext_order_no,
        issues=res.issues,
        lines=lines,
    )


# ------------------------- 范围修账 ------------------------- #


@router.post("/reconcile-range", response_model=DevReconcileRangeResult)
async def reconcile_orders_range(
    time_from: datetime = Query(...),
    time_to: datetime = Query(...),
    limit: int = Query(200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> DevReconcileRangeResult:
    svc = OrderReconcileService(session)
    results = await svc.reconcile_orders_by_created_at(
        time_from=time_from,
        time_to=time_to,
        limit=limit,
    )

    for res in results:
        await svc.apply_counters(res.order_id)

    await session.commit()

    return DevReconcileRangeResult(
        count=len(results),
        order_ids=[r.order_id for r in results],
    )


# ------------------------- summary 列表 ------------------------- #


@router.get("", response_model=List[DevOrderSummary])
async def list_orders_summary(
    session: AsyncSession = Depends(get_session),
    platform: Optional[str] = Query(None),
    shop_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    time_from: Optional[datetime] = Query(None),
    time_to: Optional[datetime] = Query(None),
    limit: int = Query(100),
) -> List[DevOrderSummary]:
    svc = DevOrdersService(session)
    rows = await svc.list_orders_summary(
        platform=platform,
        shop_id=shop_id,
        status=status,
        time_from=time_from,
        time_to=time_to,
        limit=limit,
    )

    return [
        DevOrderSummary(
            id=r["id"],
            platform=r["platform"],
            shop_id=r["shop_id"],
            ext_order_no=r["ext_order_no"],
            status=r.get("status"),
            created_at=r["created_at"],
            updated_at=r.get("updated_at"),
            warehouse_id=r.get("warehouse_id"),
            order_amount=float(r["order_amount"]) if r.get("order_amount") else None,
            pay_amount=float(r["pay_amount"]) if r.get("pay_amount") else None,
        )
        for r in rows
    ]


# ------------------------- ensure warehouse ------------------------- #


@router.post(
    "/{platform}/{shop_id}/{ext_order_no}/ensure-warehouse", response_model=DevEnsureWarehouseOut
)
async def ensure_order_warehouse(
    platform: str,
    shop_id: str,
    ext_order_no: str,
    session: AsyncSession = Depends(get_session),
) -> DevEnsureWarehouseOut:
    plat = platform.upper()

    # 查订单
    row = (
        (
            await session.execute(
                text(
                    """
                SELECT id, warehouse_id
                  FROM orders
                 WHERE platform=:p
                   AND shop_id=:s
                   AND ext_order_no=:o
                 LIMIT 1
                """
                ),
                {"p": plat, "s": shop_id, "o": ext_order_no},
            )
        )
        .mappings()
        .first()
    )

    if row is None:
        raise HTTPException(404, "order not found")

    order_id = int(row["id"])
    cur_wid = row.get("warehouse_id")

    if cur_wid is not None:
        return DevEnsureWarehouseOut(
            ok=True,
            order_id=order_id,
            platform=plat,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
            warehouse_id=cur_wid,
            source="order",
            message="order already has warehouse_id",
        )

    # 解析店铺
    store_row = (
        (
            await session.execute(
                text(
                    """
                SELECT id FROM stores
                 WHERE platform=:p
                   AND shop_id=:s
                 LIMIT 1
                """
                ),
                {"p": plat, "s": shop_id},
            )
        )
        .mappings()
        .first()
    )

    if store_row is None:
        raise HTTPException(404, "请先在【店铺管理】建立该店铺并绑定仓库")

    store_id = int(store_row["id"])

    # 解析仓库
    wid = await StoreService.resolve_default_warehouse(session, store_id=store_id)
    if wid is None:
        raise HTTPException(409, "无法解析仓库，请在店铺详情中绑定默认仓库")

    await session.execute(
        text(
            """
            UPDATE orders
               SET warehouse_id=:wid,
                   updated_at=NOW()
             WHERE id=:oid
            """
        ),
        {"wid": wid, "oid": order_id},
    )
    await session.commit()

    return DevEnsureWarehouseOut(
        ok=True,
        order_id=order_id,
        platform=plat,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        store_id=store_id,
        warehouse_id=wid,
        source="store_binding",
        message="warehouse resolved via store binding",
    )
