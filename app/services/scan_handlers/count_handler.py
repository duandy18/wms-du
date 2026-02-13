# app/services/scan_handlers/count_handler.py
from __future__ import annotations

from datetime import date, datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.stock_service import StockService
from app.services.three_books_enforcer import enforce_three_books
from app.services.utils.expiry_resolver import resolve_batch_dates_for_item

_VALID_SCOPES = {"PROD", "DRILL"}


def _norm_scope(scope: str | None) -> str:
    sc = (scope or "").strip().upper() or "PROD"
    if sc not in _VALID_SCOPES:
        raise ValueError("scope must be PROD|DRILL")
    return sc


async def handle_count(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code: str,
    actual: int,
    ref: str,
    production_date: date | None = None,
    expiry_date: date | None = None,
    trace_id: str | None = None,
    scope: str = "PROD",
) -> dict:
    """
    盘点（Count）—— v2：按 仓库 + 商品 + 批次 粒度。

    Phase 3 合同：
    - delta != 0：写 ledger + 改 stocks + snapshot 可观测一致
    - delta == 0：也写一条“确认类事件台账”（ledger），stocks 不变
      * 通过 StockService.adjust 的 allow_zero_delta_ledger + sub_reason 实现

    ✅ Scope 第一阶段：
    - stocks/ledger 必须按 scope 隔离
    """
    sc = _norm_scope(scope)

    if actual < 0:
        raise ValueError("Actual quantity must be non-negative.")
    if not batch_code or not str(batch_code).strip():
        raise ValueError("盘点操作必须提供 batch_code。")
    if warehouse_id is None or int(warehouse_id) <= 0:
        raise ValueError("盘点操作必须明确 warehouse_id。")

    bcode = str(batch_code).strip()

    # 当前库存（按 scope + warehouse + item + batch 粒度加锁读取）
    row = await session.execute(
        sa.text(
            """
            SELECT qty FROM stocks
            WHERE scope=:scope
              AND item_id=:i
              AND warehouse_id=:w
              AND batch_code IS NOT DISTINCT FROM CAST(:c AS TEXT)
            FOR UPDATE
            """
        ),
        {"scope": sc, "i": item_id, "w": warehouse_id, "c": bcode},
    )
    current = int(row.scalar_one_or_none() or 0)
    delta = int(actual) - current
    before = current
    after = current + delta

    # 只有盘盈需要按“入库”逻辑补齐日期
    if delta > 0:
        if production_date is None and expiry_date is None:
            raise ValueError("盘盈为入库行为，必须提供 production_date 或 expiry_date。")

        production_date, expiry_date = await resolve_batch_dates_for_item(
            session,
            item_id=item_id,
            production_date=production_date,
            expiry_date=expiry_date,
        )

    meta: dict[str, object] = {
        "sub_reason": "COUNT_ADJUST" if delta != 0 else "COUNT_CONFIRM",
    }
    if delta == 0:
        meta["allow_zero_delta_ledger"] = True

    stock_svc = StockService()
    await stock_svc.adjust(
        session=session,
        scope=sc,
        item_id=item_id,
        warehouse_id=warehouse_id,
        delta=delta,
        reason=MovementType.COUNT,
        ref=ref,
        ref_line=1,
        batch_code=bcode,
        production_date=production_date,
        expiry_date=expiry_date,
        trace_id=trace_id,
        meta=meta,  # type: ignore[arg-type]
    )

    ts = datetime.now(timezone.utc)
    await enforce_three_books(
        session,
        ref=str(ref),
        effects=[
            {
                "warehouse_id": int(warehouse_id),
                "item_id": int(item_id),
                "batch_code": str(bcode),
                "qty": int(delta),
                "ref": str(ref),
                "ref_line": 1,
            }
        ],
        at=ts,
    )

    return {
        "item_id": int(item_id),
        "warehouse_id": int(warehouse_id),
        "batch_code": str(batch_code),
        "actual": int(actual),
        "delta": int(delta),
        "before": int(before),
        "after": int(after),
        "production_date": production_date,
        "expiry_date": expiry_date,
    }
