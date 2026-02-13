# app/api/routers/devconsole_orders_routes_demo.py
from __future__ import annotations

import random
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.routers.devconsole_orders_schemas import DevDemoOrderOut
from app.models.enums import MovementType
from app.services.order_service import OrderService
from app.services.stock_service import StockService


def register(router: APIRouter) -> None:
    # ------------------------- 路由：生成 demo 订单 ------------------------- #

    @router.post("/demo", response_model=DevDemoOrderOut)
    async def create_demo_order(
        platform: str = Query("PDD"),
        shop_id: str = Query("1"),
        session: AsyncSession = Depends(get_session),
    ) -> DevDemoOrderOut:
        """
        生成 demo 订单（Phase 5.1 版本）：

        - 订单 ingest：给出 province=UT，让其进入 SERVICE_ASSIGNED（只写 service_warehouse_id）
        - ❌ 不再写 orders.warehouse_id（devconsole 禁止后门写入）
        - 库存 seed：仍然可以往某个仓库里落库存（这不是“订单执行仓”）
        - ✅ scope：dev demo 默认写入 DRILL（训练账本），避免污染 PROD
        """
        # 1) 随机物品（从已存在 items 里抽）
        rows = (await session.execute(text("SELECT id FROM items ORDER BY id LIMIT 10"))).fetchall()
        item_ids = [int(r[0]) for r in rows]
        if not item_ids:
            raise HTTPException(400, "items 表为空，请先添加商品。")

        # 选一个仓库用于 seed 库存（仅库存事实，不代表订单执行仓）
        wh_row = ((await session.execute(text("SELECT id FROM warehouses ORDER BY id LIMIT 1"))).mappings().first())
        if not wh_row:
            raise HTTPException(400, "warehouses 表为空，请创建至少一个仓库。")
        seed_warehouse_id = int(wh_row["id"])

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

        # 2) 落订单（Phase 5：显式给 province，进入 SERVICE_ASSIGNED）
        #    ✅ scope：dev demo 默认走 DRILL
        result = await OrderService.ingest(
            session=session,
            scope="DRILL",
            platform=plat,
            shop_id=shop,
            ext_order_no=ext_order_no,
            occurred_at=now,
            order_amount=total,
            pay_amount=total,
            items=items,
            address={"province": "UT", "receiver_name": "DEMO", "receiver_phone": "000"},
            extras=None,
            trace_id=trace_id,
        )
        order_id = int(result["id"])

        # 3) ❌ 不再绑定订单 warehouse_id（devconsole 禁止写入）

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
                scope="DRILL",
                item_id=item_id,
                warehouse_id=seed_warehouse_id,
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
