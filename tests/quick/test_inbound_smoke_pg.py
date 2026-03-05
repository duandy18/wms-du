from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.stock_service import StockService

pytestmark = pytest.mark.asyncio


async def _ensure_min_domain_v2(
    session: AsyncSession,
    *,
    warehouse_id: int = 1,
    item_id: int = 777,
) -> None:
    """
    Phase M-5：lot-world 下确保最小域存在（不再创建/触碰 legacy stocks）。
    - warehouses: id = warehouse_id
    - items     : id = item_id（policy NOT NULL）
    - item_uoms : 每 item 至少一个 base uom（PCS, ratio=1），并作为默认
    """
    # 仓库（最小一行）
    await session.execute(
        text("INSERT INTO warehouses(id, name) VALUES (:w, :name) ON CONFLICT (id) DO NOTHING"),
        {"w": warehouse_id, "name": f"WH-{warehouse_id}"},
    )

    # 商品（最小一行，Phase M-5：policy NOT NULL）
    # 设为 REQUIRED：让 smoke 用 batch_code + production_date 跑稳定的 supplier-lot 路径
    await session.execute(
        text(
            """
            INSERT INTO items(
              id, sku, name,
              lot_source_policy, expiry_policy, derivation_allowed, uom_governance_enabled,
              shelf_life_value, shelf_life_unit
            )
            VALUES(
              :i, :sku, :name,
              'SUPPLIER_ONLY'::lot_source_policy, 'REQUIRED'::expiry_policy, TRUE, TRUE,
              30, 'DAY'
            )
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"i": int(item_id), "sku": f"SKU-{item_id}", "name": f"ITEM-{item_id}"},
    )

    # 单位真相：item_uoms（base+defaults）
    await session.execute(
        text(
            """
            INSERT INTO item_uoms(
              item_id, uom, ratio_to_base, display_name,
              is_base, is_purchase_default, is_inbound_default, is_outbound_default
            )
            VALUES(
              :i, 'PCS', 1, 'PCS',
              TRUE, TRUE, TRUE, TRUE
            )
            ON CONFLICT ON CONSTRAINT uq_item_uoms_item_uom
            DO UPDATE SET
              ratio_to_base = EXCLUDED.ratio_to_base,
              display_name = EXCLUDED.display_name,
              is_base = EXCLUDED.is_base,
              is_purchase_default = EXCLUDED.is_purchase_default,
              is_inbound_default = EXCLUDED.is_inbound_default,
              is_outbound_default = EXCLUDED.is_outbound_default
            """
        ),
        {"i": int(item_id)},
    )

    await session.commit()


async def _qty_lot(session: AsyncSession, *, warehouse_id: int, item_id: int, batch_code: str | None) -> int:
    if batch_code is None:
        r = await session.execute(
            text(
                """
                SELECT COALESCE(qty, 0)
                  FROM stocks_lot
                 WHERE warehouse_id = :w
                   AND item_id = :i
                   AND lot_id IS NULL
                 LIMIT 1
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id)},
        )
        return int(r.scalar_one_or_none() or 0)

    r = await session.execute(
        text(
            """
            SELECT COALESCE(sl.qty, 0)
              FROM stocks_lot sl
              JOIN lots l ON l.id = sl.lot_id
             WHERE sl.warehouse_id = :w
               AND sl.item_id = :i
               AND l.lot_code = :c
             LIMIT 1
            """
        ),
        {"w": int(warehouse_id), "i": int(item_id), "c": str(batch_code)},
    )
    return int(r.scalar_one_or_none() or 0)


async def test_inbound_ledger_snapshot_smoke(session: AsyncSession):
    """
    入库烟雾测试（最小闭环，lot-world 余额 + ledger 一致性）：

    场景：
    1. 确保最小维度存在；
    2. 通过正式写入口（StockService.adjust）做入库 +5；
    3. 断言：
       - stocks_lot 的 qty 变化正确；
       - stock_ledger 中对应 ref/ref_line 的 after_qty 与余额一致。

    注意：
    - 本测试只验证“ledger 唯一事实 → 余额一致”的闭环。
    """
    WH, ITEM, BATCH = 1, 777, "SMOKE-BATCH-001"

    # 1) 确保最小域存在
    await _ensure_min_domain_v2(session, warehouse_id=WH, item_id=ITEM)

    svc = StockService()

    before = await _qty_lot(session, warehouse_id=WH, item_id=ITEM, batch_code=BATCH)

    # 2) 入库 +5（走 ledger 写入口）
    await svc.adjust(
        session=session,
        warehouse_id=WH,
        item_id=ITEM,
        delta=5,
        reason=MovementType.INBOUND,
        ref="SMOKE-INBOUND",
        ref_line=1,
        occurred_at=datetime.now(timezone.utc),
        batch_code=BATCH,
        production_date=date.today(),
    )
    await session.commit()

    # 3) 断言余额
    qty_now = await _qty_lot(session, warehouse_id=WH, item_id=ITEM, batch_code=BATCH)
    assert qty_now == before + 5

    # 4) 断言 ledger.after_qty 对齐余额
    row = (
        await session.execute(
            text(
                """
                SELECT delta, after_qty
                  FROM stock_ledger
                 WHERE ref = 'SMOKE-INBOUND'
                   AND ref_line = 1
                 ORDER BY id DESC
                 LIMIT 1
                """
            )
        )
    ).first()

    assert row is not None
    assert int(row.delta) == 5
    assert int(row.after_qty) == qty_now
