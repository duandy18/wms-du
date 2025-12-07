# tests/services/test_reservation_persist.py
import pytest
from sqlalchemy import text

from app.services.reservation_service import ReservationError, ReservationService
from app.services.store_service import StoreService

pytestmark = pytest.mark.asyncio


@pytest.mark.asyncio
async def test_reservation_persist_ok_and_idempotent(session):
    # 保障默认仓存在（店→仓绑定）
    platform = "PDD"
    shop = "RZ-PERSIST-01"
    store_id = await StoreService.ensure_store(
        session, platform=platform, shop_id=shop, name="RZ-PERSIST-店"
    )
    await session.execute(
        text(
            """
        INSERT INTO warehouses (id,name) VALUES (1,'WH-1') ON CONFLICT (id) DO NOTHING
    """
        )
    )
    await session.execute(
        text(
            """
        INSERT INTO store_warehouse (store_id, warehouse_id, is_default, priority)
        VALUES (:sid, 1, true, 10)
        ON CONFLICT (store_id, warehouse_id) DO UPDATE
        SET is_default=EXCLUDED.is_default, priority=EXCLUDED.priority, updated_at=now()
    """
        ),
        {"sid": store_id},
    )
    await session.commit()

    # 清理历史
    ref = "UT-RZ-PERSIST-001"
    await session.execute(
        text(
            "DELETE FROM reservation_lines WHERE reservation_id IN (SELECT id FROM reservations WHERE platform=:p AND shop_id=:s AND ref=:r)"
        ),
        {"p": platform, "s": shop, "r": ref},
    )
    await session.execute(
        text("DELETE FROM reservations WHERE platform=:p AND shop_id=:s AND ref=:r"),
        {"p": platform, "s": shop, "r": ref},
    )
    await session.commit()

    # 1) 首次持久化
    r1 = await ReservationService.reserve_persist(
        session,
        platform=platform,
        shop_id=shop,
        ref=ref,
        lines=[{"item_id": 1001, "qty": 2}, {"item_id": 1002, "qty": 3}],
    )
    await session.commit()
    assert r1["status"] == "OK"
    rid = r1["reservation_id"]

    # 2) 再次调用（幂等）
    r2 = await ReservationService.reserve_persist(
        session,
        platform=platform,
        shop_id=shop,
        ref=ref,
        lines=[{"item_id": 1001, "qty": 2}],
    )
    await session.commit()
    assert r2["status"] == "IDEMPOTENT"
    assert r2["reservation_id"] == rid

    # 3) 验证表里确实有 2 条行（以第一次的输入为准，第二次不再新增）
    c = await session.execute(
        text(
            """
        SELECT COUNT(*) FROM reservation_lines WHERE reservation_id=:rid
    """
        ),
        {"rid": rid},
    )
    assert (c.scalar() or 0) == 2

    # 4) 不落 ledger（COUNT 之前）
    lc = await session.execute(text("SELECT COUNT(*) FROM stock_ledger WHERE reason='PICK'"))
    assert (lc.scalar() or 0) == 0


@pytest.mark.asyncio
async def test_reservation_persist_error_when_no_default_warehouse(session):
    # 不绑定默认仓：不传 warehouse_id 会报错
    platform = "PDD"
    shop = "RZ-PERSIST-NODEF"
    # 只建店，不绑仓
    await StoreService.ensure_store(session, platform=platform, shop_id=shop, name="RZ-NODEF-店")
    await session.commit()

    with pytest.raises(ReservationError):
        await ReservationService.reserve_persist(
            session,
            platform=platform,
            shop_id=shop,
            ref="UT-NODEF-001",
            lines=[{"item_id": 1001, "qty": 1}],
        )
