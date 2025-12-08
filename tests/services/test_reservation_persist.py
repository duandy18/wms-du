# tests/services/test_reservation_persist.py
import pytest
from sqlalchemy import text

from app.services.soft_reserve_service import SoftReserveService
from app.services.store_service import StoreService

pytestmark = pytest.mark.asyncio


@pytest.mark.asyncio
async def test_reservation_persist_ok_and_idempotent(session):
    """
    升级语义版合同：

    使用 SoftReserveService.persist 做软预占持久化（不动库存、不写 ledger），
    验证：

      1) 首次 persist 返回 OK 且给出 reservation_id；
      2) 再次对同一业务键(platform/shop/wh/ref) 调用 persist（即幂等重放）：
           - reservation_id 不变；
           - reservation_lines 行数保持不变（以首次输入为准）；
      3) 不写任何 ledger（reason='PICK' 等）。
    """
    platform = "PDD"
    shop = "RZ-PERSIST-01"

    # 保障默认仓存在（只为方便选一个 wh_id，SoftReserve 本身不依赖 StoreService）
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

    warehouse_id = 1

    # 清理历史
    ref = "UT-RZ-PERSIST-001"
    await session.execute(
        text(
            "DELETE FROM reservation_lines WHERE reservation_id IN "
            "(SELECT id FROM reservations WHERE platform=:p AND shop_id=:s AND ref=:r)"
        ),
        {"p": platform, "s": shop, "r": ref},
    )
    await session.execute(
        text("DELETE FROM reservations WHERE platform=:p AND shop_id=:s AND ref=:r"),
        {"p": platform, "s": shop, "r": ref},
    )
    await session.commit()

    svc = SoftReserveService()

    # 1) 首次持久化
    r1 = await svc.persist(
        session,
        platform=platform,
        shop_id=shop,
        warehouse_id=warehouse_id,
        ref=ref,
        lines=[{"item_id": 1001, "qty": 2}, {"item_id": 1002, "qty": 3}],
    )
    await session.commit()
    assert r1.get("status") == "OK"
    rid = r1["reservation_id"]

    # 2) 再次调用（幂等），用较少的行作为输入：不再新增行、只更新现有 ref_line=1
    r2 = await svc.persist(
        session,
        platform=platform,
        shop_id=shop,
        warehouse_id=warehouse_id,
        ref=ref,
        lines=[{"item_id": 1001, "qty": 2}],
    )
    await session.commit()
    # 当前实现不区分 OK/IDEMPOTENT，只要 reservation_id 相同即可
    assert r2.get("status") == "OK"
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
    assert int(c.scalar() or 0) == 2

    # 4) 不落 ledger（尤其是 PICK 等理由）
    lc = await session.execute(text("SELECT COUNT(*) FROM stock_ledger WHERE reason='PICK'"))
    assert int(lc.scalar() or 0) == 0


@pytest.mark.skip(
    reason=(
        "legacy: 早期 reserve_persist 会在未绑定默认仓时报错；"
        "当前 SoftReserveService.persist 一律要求显式 warehouse_id，"
        "默认仓解析逻辑已经上移到订单/路由层，不再由 soft reserve 负责。"
    )
)
@pytest.mark.asyncio
async def test_reservation_persist_error_when_no_default_warehouse(session):
    """
    旧世界观：ReservationService.reserve_persist 会在“没有默认仓”时抛 ReservationError。

    新世界观下：
      - SoftReserveService.persist 总是要求调用方明确传入 warehouse_id；
      - “店铺→默认仓”的解析由更高一层的订单/路由服务负责；
      - 因此这里标记为 skip，仅保留历史语义说明。
    """
    pass
