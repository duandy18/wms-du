# app/api/routers/dev_seed_ledger.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.enums import MovementType
from app.services.stock_service import StockService

router = APIRouter(prefix="/dev", tags=["dev-seed"])


async def _pick_one_warehouse_and_item(session: AsyncSession) -> tuple[int, int]:
    """
    复用现有主数据：
    - warehouses 取 1 个 id
    - items 取 1 个 id
    """
    wh_row = (
        (await session.execute(text("SELECT id FROM warehouses ORDER BY id LIMIT 1")))
        .mappings()
        .first()
    )
    if not wh_row:
        raise HTTPException(status_code=400, detail="dev seed 失败：warehouses 表为空，请先创建至少一个仓库。")
    warehouse_id = int(wh_row["id"])

    item_row = (await session.execute(text("SELECT id FROM items ORDER BY id LIMIT 1"))).mappings().first()
    if not item_row:
        raise HTTPException(status_code=400, detail="dev seed 失败：items 表为空，请先创建至少一个商品。")
    item_id = int(item_row["id"])

    return warehouse_id, item_id


@router.post("/seed-ledger-test")
async def seed_ledger_test(session: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
    """
    dev 测试初始化：
    - scope=DRILL，避免污染 PROD
    - 用固定 ref/ref_line/batch_code 保证幂等
    - 生成：RECEIPT(+10) -> SHIP(-4) -> ADJUSTMENT(调整到 5)
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

        slot_row = (
            (
                await session.execute(
                    text(
                        """
                        SELECT qty
                          FROM stocks
                         WHERE scope = 'DRILL'
                           AND warehouse_id = :w
                           AND item_id = :i
                           AND batch_code = :b
                         LIMIT 1
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
            results.append({"step": "COUNT", "result": {"idempotent": True, "applied": False, "skip": True}})

        await session.commit()

    except Exception:
        await session.rollback()
        raise

    return {"ok": True, "warehouse_id": wh_id, "item_id": item_id, "batch_code": batch_code, "results": results}


@router.post("/seed-stock-target")
async def seed_stock_target(
    payload: Dict[str, Any] = Body(...),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """
    定向把 (scope, warehouse_id, item_id, batch_code) 的库存调整到 target_qty（通过 StockService.adjust 写台账）。

    支持两种批次模式：
    - 显式指定 batch_code 字符串：用于普通批次槽位
    - 显式传 batch_code=null 或 ""：用于 __NULL_BATCH__ 槽位（batch_code IS NULL）

    注意：
    - 若请求体不包含 batch_code 字段，则默认 "AUTO"（保持原有行为）
    """
    scope = str(payload.get("scope") or "DRILL").strip().upper()
    warehouse_id = payload.get("warehouse_id")
    item_id = payload.get("item_id")
    target_qty = payload.get("target_qty")

    # ✅ batch_code 语义：
    # - 未传 batch_code：默认 "AUTO"
    # - 显式传 null / ""：batch_code=None（__NULL_BATCH__）
    # - 传字符串：按字符串
    if "batch_code" in payload:
        raw_batch = payload.get("batch_code")
        if raw_batch in (None, ""):
            batch_code: Optional[str] = None
        else:
            batch_code = str(raw_batch).strip()
            if not batch_code:
                batch_code = None
    else:
        batch_code = "AUTO"

    ref = str(payload.get("ref") or "dev:seed:stock:target").strip()
    ref_line = int(payload.get("ref_line") or 1)

    if not warehouse_id or int(warehouse_id) <= 0:
        raise HTTPException(status_code=422, detail="warehouse_id is required (>=1)")
    if not item_id or int(item_id) <= 0:
        raise HTTPException(status_code=422, detail="item_id is required (>=1)")
    if target_qty is None or int(target_qty) < 0:
        raise HTTPException(status_code=422, detail="target_qty is required (>=0)")

    wh_id = int(warehouse_id)
    it_id = int(item_id)
    tgt = int(target_qty)

    # 读取当前槽位 qty（batch_code=None 时使用 IS NULL）
    if batch_code is None:
        slot_row = (
            (
                await session.execute(
                    text(
                        """
                        SELECT qty
                          FROM stocks
                         WHERE scope = :scope
                           AND warehouse_id = :w
                           AND item_id = :i
                           AND batch_code IS NULL
                         LIMIT 1
                        """
                    ),
                    {"scope": scope, "w": wh_id, "i": it_id},
                )
            )
            .mappings()
            .first()
        )
    else:
        slot_row = (
            (
                await session.execute(
                    text(
                        """
                        SELECT qty
                          FROM stocks
                         WHERE scope = :scope
                           AND warehouse_id = :w
                           AND item_id = :i
                           AND batch_code = :b
                         LIMIT 1
                        """
                    ),
                    {"scope": scope, "w": wh_id, "i": it_id, "b": batch_code},
                )
            )
            .mappings()
            .first()
        )

    current_qty = int(slot_row["qty"] or 0) if slot_row else 0
    delta = tgt - current_qty

    if delta == 0:
        return {
            "ok": True,
            "skip": True,
            "scope": scope,
            "warehouse_id": wh_id,
            "item_id": it_id,
            "batch_code": batch_code,
            "current_qty": current_qty,
            "target_qty": tgt,
            "delta": 0,
        }

    stock_service = StockService()
    now = datetime.now(timezone.utc)

    try:
        r = await stock_service.adjust(
            session=session,
            scope=scope,
            item_id=it_id,
            warehouse_id=wh_id,
            delta=delta,
            reason=MovementType.ADJUSTMENT,
            ref=ref,
            ref_line=ref_line,
            occurred_at=now,
            batch_code=batch_code,  # ✅ 允许 None（__NULL_BATCH__）
            trace_id="dev-seed-stock-target",
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    return {
        "ok": True,
        "scope": scope,
        "warehouse_id": wh_id,
        "item_id": it_id,
        "batch_code": batch_code,
        "current_qty": current_qty,
        "target_qty": tgt,
        "delta": delta,
        "result": r,
    }
