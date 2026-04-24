from datetime import date, timedelta, datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.shared.enums import MovementType
from app.wms.outbound.services.outbound_commit_service import ship_commit
from app.wms.stock.services.stock_service import StockService
from tests.services._helpers import ensure_store


async def _requires_batch(session: AsyncSession, item_id: int) -> bool:
    """
    Phase M 第一阶段：测试也不再读取 has_shelf_life（镜像字段）。
    批次受控唯一真相源：items.expiry_policy == 'REQUIRED'
    """
    row = await session.execute(
        text("SELECT expiry_policy FROM items WHERE id=:i LIMIT 1"),
        {"i": int(item_id)},
    )
    v = row.scalar_one_or_none()
    return str(v or "").strip().upper() == "REQUIRED"


async def _slot_code(session: AsyncSession, item_id: int) -> str | None:
    # 批次受控 => 用 NEAR；非批次 => 用无展示码内部槽位
    return "NEAR" if await _requires_batch(session, item_id) else None


def _required_dates_for_code(code: str) -> tuple[date, date]:
    # quick 测试里固定给一组稳定日期即可
    prod = date(2030, 1, 1)
    exp = prod + timedelta(days=365)
    return prod, exp


async def _ensure_order_ref_exists(session: AsyncSession, *, order_ref: str) -> None:
    parts = str(order_ref).split(":", 2)
    assert len(parts) == 3, f"invalid test order_ref: {order_ref}"
    platform, shop_id, ext_order_no = parts
    store_id = await ensure_store(
        session,
        platform=str(platform).upper(),
        shop_id=str(shop_id),
        name=f"UT-{str(platform).upper()}-{shop_id}",
    )
    await session.execute(
        text(
            """
            INSERT INTO orders(platform, shop_id, store_id, ext_order_no, status, created_at, updated_at)
            VALUES (:p, :sid, :store_id, :ext, 'CREATED', now(), now())
            ON CONFLICT ON CONSTRAINT uq_orders_platform_shop_ext DO UPDATE
              SET store_id = EXCLUDED.store_id,
                  updated_at = EXCLUDED.updated_at
            """
        ),
        {
            "p": str(platform).upper(),
            "sid": str(shop_id),
            "store_id": int(store_id),
            "ext": str(ext_order_no),
            "created_at": datetime.now(timezone.utc),
        },
    )
    await session.commit()


async def _qty(session: AsyncSession, item_id: int, wh: int, code: str | None) -> int:
    if code is None:
        r = await session.execute(
            text(
                """
                SELECT COALESCE(qty, 0)
                  FROM stocks_lot
                 WHERE item_id=:i
                   AND warehouse_id=:w
                 LIMIT 1
                """
            ),
            {"i": int(item_id), "w": int(wh)},
        )
        return int(r.scalar_one_or_none() or 0)

    r = await session.execute(
        text(
            """
            SELECT COALESCE(sl.qty, 0)
              FROM stocks_lot sl
              JOIN lots l ON l.id = sl.lot_id
             WHERE sl.item_id=:i
               AND sl.warehouse_id=:w
               AND l.lot_code = :c
             LIMIT 1
            """
        ),
        {"i": int(item_id), "w": int(wh), "c": str(code)},
    )
    return int(r.scalar_one_or_none() or 0)


async def _ensure_stock_seed(session: AsyncSession, *, item_id: int, wh: int, code: str | None, qty: int) -> None:
    """
    强护栏下不要依赖 conftest 的隐式基线库存，测试必须显式 seed 目标槽位。
    """
    svc = StockService()
    before = await _qty(session, item_id, wh, code)
    if before >= qty:
        return

    need = qty - before
    if code is None:
        await svc.adjust(
            session=session,
            item_id=int(item_id),
            warehouse_id=int(wh),
            delta=int(need),
            reason=MovementType.INBOUND,
            ref=f"UT-SEED-QOUT-{item_id}-{wh}-NULL",
            ref_line=1,
            occurred_at=None,
            batch_code=None,
        )
    else:
        prod, exp = _required_dates_for_code(str(code))
        await svc.adjust(
            session=session,
            item_id=int(item_id),
            warehouse_id=int(wh),
            delta=int(need),
            reason=MovementType.INBOUND,
            ref=f"UT-SEED-QOUT-{item_id}-{wh}-{code}",
            ref_line=1,
            occurred_at=None,
            batch_code=str(code),
            production_date=prod,
            expiry_date=exp,
        )
    await session.commit()


@pytest.mark.asyncio
async def test_outbound_idem_and_insufficient(session: AsyncSession):
    """
    v2 出库合同（quick）：

    场景：
      - item 3003 在仓 1 的“目标槽位”有库存 >=1；
      - 同一个 order_id=Q-OUT-1 重复 ship_commit 两次，只扣一次；
      - 另一单 Q-OUT-2 请求超量，抛 409(outbound_commit_reject)，details.results 至少一条 INSUFFICIENT。

    槽位口径（与后端 requires_batch 派生一致）：
      - 批次受控：batch_code='NEAR'
      - 非批次受控：batch_code=NULL（内部槽位）
    """
    item_id, wh = 3003, 1
    code = await _slot_code(session, item_id)

    # ✅ 显式 seed，保证 before >= 1
    await _ensure_stock_seed(session, item_id=item_id, wh=wh, code=code, qty=10)

    before = await _qty(session, item_id, wh, code)
    assert before >= 1

    # 幂等（两次同一单据，不应重复扣减）
    order_id = "UT:PH3:Q-OUT-1"
    await _ensure_order_ref_exists(session, order_ref=order_id)
    lines = [{"item_id": item_id, "warehouse_id": wh, "batch_code": code, "qty": 1}]
    r1 = await ship_commit(session, order_id=order_id, lines=lines, warehouse_code="WH-1")
    r2 = await ship_commit(session, order_id=order_id, lines=lines, warehouse_code="WH-1")
    assert r1["status"] == "OK" and r2["status"] == "OK"

    mid = await _qty(session, item_id, wh, code)
    assert mid == before - 1

    # 不足：同一槽位请求超量 => 409(outbound_commit_reject)
    await _ensure_order_ref_exists(session, order_ref="UT:PH3:Q-OUT-2")

    with pytest.raises(HTTPException) as ei:
        await ship_commit(
            session,
            order_id="UT:PH3:Q-OUT-2",
            lines=[{"item_id": item_id, "warehouse_id": wh, "batch_code": code, "qty": 9999}],
            warehouse_code="WH-1",
        )

    e = ei.value
    assert e.status_code == 409
    detail = e.detail
    assert isinstance(detail, dict)
    assert detail.get("error_code") == "outbound_commit_reject"

    # details[0].results 至少有一条 INSUFFICIENT
    details = detail.get("details") or []
    assert details and isinstance(details[0], dict)
    results = details[0].get("results") or []
    assert any(x.get("status") == "INSUFFICIENT" for x in results)
