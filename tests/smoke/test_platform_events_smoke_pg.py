# tests/smoke/test_platform_events_smoke_pg.py
"""
多平台平台事件 → pipeline 冒烟测试（v2 schema 版）。
"""

import os
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.enums import MovementType
from tests.services._helpers import ensure_store
from app.services.platform_events import handle_event_batch
from app.services.stock_service import StockService

ASYNC_URL = (
    os.getenv("WMS_TEST_DATABASE_URL")
    or os.getenv("WMS_DATABASE_URL")
    or "postgresql+asyncpg://postgres:wms@127.0.0.1:55432/postgres"
)


async def _ensure_item_with_uoms(session: AsyncSession, *, item_id: int) -> None:
    """
    Phase M-5 最小合法 item + item_uoms：
    - items: policy NOT NULL（无默认）
    - item_uoms: 单位真相源唯一（至少 base + defaults）
    - 这里为了让 StockService.adjust 的 batch/date 路径稳定，设为 expiry_policy=REQUIRED 并给 shelf_life 参数
    """
    await session.execute(
        text(
            """
            INSERT INTO items(
              id, sku, name,
              lot_source_policy, expiry_policy, derivation_allowed, uom_governance_enabled,
              shelf_life_value, shelf_life_unit
            )
            VALUES(
              :id, :sku, :name,
              'SUPPLIER_ONLY'::lot_source_policy, 'REQUIRED'::expiry_policy, TRUE, TRUE,
              30, 'DAY'
            )
            ON CONFLICT (id) DO UPDATE
              SET name = EXCLUDED.name,
                  lot_source_policy = EXCLUDED.lot_source_policy,
                  expiry_policy = EXCLUDED.expiry_policy,
                  derivation_allowed = EXCLUDED.derivation_allowed,
                  uom_governance_enabled = EXCLUDED.uom_governance_enabled,
                  shelf_life_value = EXCLUDED.shelf_life_value,
                  shelf_life_unit = EXCLUDED.shelf_life_unit
            """
        ),
        {"id": int(item_id), "sku": f"SKU-{item_id}", "name": f"ITEM-{item_id}"},
    )

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


@pytest.mark.asyncio
async def test_smoke_multi_platform_end2end():
    eng = create_async_engine(ASYNC_URL, future=True)
    Session = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)

    async with Session() as s:
        # ---------- 1) 维度与初始库存 ----------
        await s.execute(text("INSERT INTO warehouses (id, name) VALUES (1,'WH-1') ON CONFLICT (id) DO NOTHING"))

        # Phase M-5：items + item_uoms（单位真相源）
        await _ensure_item_with_uoms(s, item_id=1)
        await _ensure_item_with_uoms(s, item_id=2)
        await _ensure_item_with_uoms(s, item_id=3)

        # Phase 4E：不再直写 legacy stocks，统一走 ledger 写入口 seed
        svc = StockService()
        now = datetime.now(timezone.utc)
        await svc.adjust(
            session=s,
            warehouse_id=1,
            item_id=1,
            delta=10,
            reason=MovementType.INBOUND,
            ref="SMOKE-SEED-1",
            ref_line=1,
            occurred_at=now,
            batch_code="B-1",
            production_date=date.today(),
        )
        await svc.adjust(
            session=s,
            warehouse_id=1,
            item_id=2,
            delta=20,
            reason=MovementType.INBOUND,
            ref="SMOKE-SEED-2",
            ref_line=1,
            occurred_at=now,
            batch_code="B-2",
            production_date=date.today(),
        )
        await svc.adjust(
            session=s,
            warehouse_id=1,
            item_id=3,
            delta=5,
            reason=MovementType.INBOUND,
            ref="SMOKE-SEED-3",
            ref_line=1,
            occurred_at=now,
            batch_code="B-3",
            production_date=date.today(),
        )
        await s.commit()

        # ---------- 2) Phase 5：预置 orders（使 ship commit 可解析到 orders.id） ----------
        # 注意：事件里用的是 ext_order_no-only（如 P-SMOKE-001），Phase 5 第二刀要求先能解析到 orders.id。
        ref_p, ref_t, ref_j = "P-SMOKE-001", "T-SMOKE-002", "J-SMOKE-003"
        pdd_store_id = await ensure_store(s, platform="PDD", shop_id="SMOKE", name="UT-PDD-SMOKE")
        tb_store_id = await ensure_store(s, platform="TAOBAO", shop_id="SMOKE", name="UT-TAOBAO-SMOKE")
        jd_store_id = await ensure_store(s, platform="JD", shop_id="SMOKE", name="UT-JD-SMOKE")
        await s.execute(
            text(
                """
                INSERT INTO orders(platform, shop_id, store_id, ext_order_no)
                VALUES
                  ('PDD',    'SMOKE', :pdd_store_id, :p),
                  ('TAOBAO', 'SMOKE', :tb_store_id, :t),
                  ('JD',     'SMOKE', :jd_store_id, :j)
                ON CONFLICT (platform, shop_id, ext_order_no) DO UPDATE
                  SET store_id = EXCLUDED.store_id
                """
            ),
            {
                "p": ref_p,
                "t": ref_t,
                "j": ref_j,
                "pdd_store_id": int(pdd_store_id),
                "tb_store_id": int(tb_store_id),
                "jd_store_id": int(jd_store_id),
            },
        )
        await s.commit()

        # ---------- 3) 多平台“已发货”事件 ----------
        pdd_order_ref = f"ORD:PDD:SMOKE:{ref_p}"
        tb_order_ref = f"ORD:TAOBAO:SMOKE:{ref_t}"
        jd_order_ref = f"ORD:JD:SMOKE:{ref_j}"

        events = [
            {
                "platform": "pdd",
                "order_sn": pdd_order_ref,
                "status": "SHIPPED",
                "lines": [{"item_id": 1, "warehouse_id": 1, "batch_code": "B-1", "qty": 2}],
            },
            {
                "platform": "taobao",
                "tid": tb_order_ref,
                "trade_status": "WAIT_BUYER_CONFIRM_GOODS",
                "lines": [{"item_id": 2, "warehouse_id": 1, "batch_code": "B-2", "qty": 5}],
            },
            {
                "platform": "jd",
                "orderId": jd_order_ref,
                "orderStatus": "DELIVERED",
                "lines": [{"item_id": 3, "warehouse_id": 1, "batch_code": "B-3", "qty": 1}],
            },
        ]

        await handle_event_batch(events, session=s)
        await s.commit()

        # ---------- 4) 校验 lot-world 余额存在 ----------
        rows = (
            await s.execute(
                text(
                    """
                    SELECT item_id, COALESCE(SUM(qty), 0) AS qty
                      FROM stocks_lot
                     WHERE warehouse_id = 1
                       AND item_id IN (1,2,3)
                     GROUP BY item_id
                     ORDER BY item_id
                    """
                )
            )
        ).all()
        qtys = {int(r[0]): int(r[1]) for r in rows}
        assert set(qtys.keys()) == {1, 2, 3}
        assert all(q >= 0 for q in qtys.values())

        # ---------- 5) 重放相同事件 → 应该仍然不抛异常 ----------
        await handle_event_batch(events, session=s)
        await s.commit()
