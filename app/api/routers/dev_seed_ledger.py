# app/api/routers/dev_seed_ledger.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.enums import MovementType
from app.services.stock_service import StockService

router = APIRouter(prefix="/dev", tags=["dev-seed"])


async def _pick_one_warehouse_and_item(
    session: AsyncSession,
) -> tuple[int, int]:
    """
    尽量复用现有主数据：
    - 从 warehouses 里拿一个 id
    - 从 items 里拿一个 id

    若任一为空，直接报 400，让调用方先准备基础数据。
    """
    wh_row = (
        (await session.execute(text("SELECT id FROM warehouses ORDER BY id LIMIT 1")))
        .mappings()
        .first()
    )
    if not wh_row:
        raise HTTPException(
            status_code=400,
            detail="dev seed 失败：warehouses 表为空，请先创建至少一个仓库。",
        )
    warehouse_id = int(wh_row["id"])

    item_row = (
        (await session.execute(text("SELECT id FROM items ORDER BY id LIMIT 1"))).mappings().first()
    )
    if not item_row:
        raise HTTPException(
            status_code=400,
            detail="dev seed 失败：items 表为空，请先创建至少一个商品。",
        )
    item_id = int(item_row["id"])

    return warehouse_id, item_id


@router.post("/seed-ledger-test")
async def seed_ledger_test(
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """
    dev 用测试初始化接口：

    复用库里已有的 1 个 warehouse + 1 个 item，生成以下三笔台账：

    1) 入库：  +10（RECEIPT，batch=B-TEST-LEDGER）
    2) 出库：   -4（SHIPMENT）
    3) 盘点：   调整到 5（ADJUSTMENT/COUNT）

    幂等设计：
    - 所有调用都用固定 ref / ref_line / batch_code
    - StockService.adjust + ledger 唯一约束保障幂等
    - 重复调用不会重复扣减，只会返回 idempotent=True。

    注意：
    - 这里显式调用 session.commit()，确保写入持久化到 DB。
    - ✅ scope：dev seed 默认写入 DRILL（训练账本），避免污染 PROD。
    """

    wh_id, item_id = await _pick_one_warehouse_and_item(session)

    stock_service = StockService()
    utc = timezone.utc
    now = datetime.now(utc)

    batch_code = "B-TEST-LEDGER"
    prod_date = date.today()
    exp_date = prod_date + timedelta(days=365)

    results: List[Dict[str, Any]] = []

    try:
        # 1) 入库 +10
        r1 = await stock_service.adjust(
            session=session,
            scope="DRILL",
            item_id=item_id,
            warehouse_id=wh_id,
            delta=10,
            reason=MovementType.RECEIPT,
            ref="seed:receipt:1",
            ref_line=1,
            occurred_at=now,
            batch_code=batch_code,
            production_date=prod_date,
            expiry_date=exp_date,
            trace_id="seed-trace-receipt",
        )
        results.append({"step": "RECEIPT +10", "result": r1})

        # 2) 出库 -4
        r2 = await stock_service.adjust(
            session=session,
            scope="DRILL",
            item_id=item_id,
            warehouse_id=wh_id,
            delta=-4,
            reason=MovementType.SHIP,
            ref="seed:ship:1",
            ref_line=1,
            occurred_at=now + timedelta(seconds=1),
            batch_code=batch_code,
            trace_id="seed-trace-ship",
        )
        results.append({"step": "SHIP -4", "result": r2})

        # 3) 盘点：把库存调整到 5
        slot_row = (
            (
                await session.execute(
                    text(
                        """
                    SELECT qty FROM stocks
                    WHERE scope = 'DRILL'
                      AND warehouse_id = :w
                      AND item_id = :i
                      AND batch_code = :b
                    """
                    ),
                    {"w": wh_id, "i": item_id, "b": batch_code},
                )
            )
            .mappings()
            .first()
        )

        current_qty = int(slot_row["qty"] or 0) if slot_row else 0
        target_qty = 5
        delta_count = target_qty - current_qty

        if delta_count != 0:
            r3 = await stock_service.adjust(
                session=session,
                scope="DRILL",
                item_id=item_id,
                warehouse_id=wh_id,
                delta=delta_count,
                reason=MovementType.ADJUSTMENT,
                ref="seed:count:1",
                ref_line=1,
                occurred_at=now + timedelta(seconds=2),
                batch_code=batch_code,
                trace_id="seed-trace-count",
            )
            results.append({"step": f"COUNT delta={delta_count}", "result": r3})
        else:
            results.append(
                {
                    "step": "COUNT",
                    "result": {
                        "idempotent": True,
                        "applied": False,
                        "skip": True,
                        "note": "already at target 5",
                    },
                }
            )

        # ✅ 关键：所有调整完成后提交事务
        await session.commit()

    except Exception:
        # 出错时回滚，抛给全局异常处理
        await session.rollback()
        raise

    return {
        "ok": True,
        "warehouse_id": wh_id,
        "item_id": item_id,
        "batch_code": batch_code,
        "results": results,
    }
