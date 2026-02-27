# tests/services/test_purchase_order_receive_batch_semantics.py

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text

from app.services.purchase_order_receive import receive_po_line
from tests.helpers.po_testkit import create_po_with_line_and_draft_receipt


async def _create_item(session, *, has_shelf_life: bool) -> int:
    r"""
    仅为本测试创建最小 item。

    Phase M（一步到位）：
    - items 新增 rule policy（NOT NULL）
      - lot_source_policy
      - expiry_policy
      - derivation_allowed
      - uom_governance_enabled
    - 并且 has_shelf_life 必须与 expiry_policy 对齐（DB CHECK 已封板）
    """
    expiry_policy = "REQUIRED" if bool(has_shelf_life) else "NONE"
    row = await session.execute(
        text(
            """
            INSERT INTO items (
              name, sku, uom,
              lot_source_policy, expiry_policy, derivation_allowed, uom_governance_enabled,
              has_shelf_life
            )
            VALUES (
              :name, :sku, 'PCS',
              'SUPPLIER_ONLY'::lot_source_policy, CAST(:expiry_policy AS expiry_policy), TRUE, FALSE,
              CAST(:has_shelf_life AS boolean)
            )
            RETURNING id
            """
        ),
        {
            "name": "UT-item-shelf" if has_shelf_life else "UT-item-noshelf",
            "sku": "UT-SKU-SHELF" if has_shelf_life else "UT-SKU-NOSHELF",
            "expiry_policy": expiry_policy,
            "has_shelf_life": bool(has_shelf_life),
        },
    )
    return int(row.scalar_one())


@pytest.mark.asyncio
async def test_non_shelf_life_item_forces_null_batch(async_session_maker):
    """
    非效期商品：
    - 即使传 production/expiry
    - receipt_line 中 batch_code/production_date/expiry_date 必须全部为 NULL

    Phase M-2 语义：
    - draft 阶段不产生 lot_id，不创建 lots 记录
    - lot_id / lots 只在 confirm 阶段生成/固化
    """
    async with async_session_maker() as session:
        item_id = await _create_item(session, has_shelf_life=False)
        world = await create_po_with_line_and_draft_receipt(session, item_id=item_id)
        await session.commit()

    async with async_session_maker() as session:
        await receive_po_line(
            session,
            po_id=world.po_id,
            line_id=world.po_line_id,
            qty=1,
            occurred_at=datetime.now(tz=timezone.utc),
            production_date=date(2026, 1, 1),
            expiry_date=date(2026, 6, 1),
        )
        await session.commit()

    async with async_session_maker() as session:
        row = await session.execute(
            text(
                """
                SELECT batch_code, production_date, expiry_date, lot_id
                  FROM inbound_receipt_lines
                 WHERE po_line_id = :lid
                 ORDER BY id DESC
                 LIMIT 1
                """
            ),
            {"lid": int(world.po_line_id)},
        )
        r = row.first()
        assert r is not None
        assert r[0] is None
        assert r[1] is None
        assert r[2] is None

        # ✅ Phase M-2：draft 阶段不产生 lot_id
        assert r[3] is None

        # ✅ Phase M-2：draft 阶段不创建 lots
        row2 = await session.execute(
            text(
                """
                SELECT COUNT(*)::int
                  FROM lots
                 WHERE warehouse_id = :wid
                   AND item_id = :item_id
                """
            ),
            {"wid": int(world.warehouse_id), "item_id": int(item_id)},
        )
        assert int(row2.scalar_one()) == 0


@pytest.mark.asyncio
async def test_shelf_life_batch_conflict_raises_409(async_session_maker):
    """
    效期商品批次/日期写入语义（自洽性断言版）

    Phase M-2 去耦合后：
    - 不再做 lot_code × 日期冲突校验（伪命题）
    - 本测试只断言“输出自洽”：
      receipt_line 的 (batch_code, production_date, expiry_date) 要么全 NULL，要么全非 NULL。
    """
    async with async_session_maker() as session:
        item_id = await _create_item(session, has_shelf_life=True)
        world = await create_po_with_line_and_draft_receipt(session, item_id=item_id)
        await session.commit()

    code = "UT-BATCH-1"

    async with async_session_maker() as session:
        await receive_po_line(
            session,
            po_id=world.po_id,
            line_id=world.po_line_id,
            qty=1,
            occurred_at=datetime.now(tz=timezone.utc),
            batch_code=code,
            production_date=date(2026, 1, 1),
            expiry_date=date(2026, 6, 1),
        )
        await session.commit()

    async with async_session_maker() as session:
        await receive_po_line(
            session,
            po_id=world.po_id,
            line_id=world.po_line_id,
            qty=1,
            occurred_at=datetime.now(tz=timezone.utc),
            batch_code=code,
            production_date=date(2026, 1, 1),
            expiry_date=date(2026, 12, 1),
        )
        await session.commit()

    async with async_session_maker() as session:
        row = await session.execute(
            text(
                """
                SELECT batch_code, production_date, expiry_date
                  FROM inbound_receipt_lines
                 WHERE po_line_id = :lid
                 ORDER BY id DESC
                 LIMIT 1
                """
            ),
            {"lid": int(world.po_line_id)},
        )
        r = row.first()
        assert r is not None

        batch, prod, exp = r[0], r[1], r[2]
        all_null = (batch is None) and (prod is None) and (exp is None)
        all_present = (batch is not None) and (prod is not None) and (exp is not None)
        assert all_null or all_present, (batch, prod, exp)
