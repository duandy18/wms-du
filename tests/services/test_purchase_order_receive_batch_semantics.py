# tests/services/test_purchase_order_receive_batch_semantics.py

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.services.purchase_order_receive import receive_po_line
from tests.helpers.po_testkit import create_po_with_line_and_draft_receipt


async def _create_item(session, *, has_shelf_life: bool) -> int:
    r"""
    仅为本测试创建最小 item。

    ⚠️ 提醒（工程规则）：
    - 若 items 表出现更多 NOT NULL/约束，请优先复用现有 seed/fixture；
    - 或先用 psql 查看真实表结构再调整插入字段，例如：
      psql -c "\d+ items"
    """
    row = await session.execute(
        text(
            """
            INSERT INTO items (name, sku, has_shelf_life)
            VALUES (:name, :sku, :has_shelf_life)
            RETURNING id
            """
        ),
        {
            "name": "UT-item-shelf" if has_shelf_life else "UT-item-noshelf",
            "sku": "UT-SKU-SHELF" if has_shelf_life else "UT-SKU-NOSHELF",
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

    Phase 4E（lot-world）：
    - 该用例不得触碰 legacy batches；
    - 并且不应为该商品创建 lots（因为 batch 语义被强制归一为 NULL 槽位）。
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
        # lot-world：非效期商品强制 NULL 槽位，不应绑定 lot
        assert r[3] is None

        # ✅ lots 不得新增记录（该 item_id 在本测试中是新建的，断言可严格为 0）
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
    效期商品同批次冲突：
    - 第一次写入成功（创建 canonical）
    - 第二次同 batch_code 但 expiry_date 改掉
    - 必须抛 HTTP 409
    """
    async with async_session_maker() as session:
        item_id = await _create_item(session, has_shelf_life=True)
        world = await create_po_with_line_and_draft_receipt(session, item_id=item_id)
        await session.commit()

    # 第一次：建立 canonical
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

    # 第二次：同 batch_code（由 production_date 决定），但 expiry_date 改掉 -> 409
    async with async_session_maker() as session:
        with pytest.raises(HTTPException) as exc:
            await receive_po_line(
                session,
                po_id=world.po_id,
                line_id=world.po_line_id,
                qty=1,
                occurred_at=datetime.now(tz=timezone.utc),
                production_date=date(2026, 1, 1),
                expiry_date=date(2026, 12, 1),
            )
        assert exc.value.status_code == 409
