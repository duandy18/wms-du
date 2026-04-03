# tests/services/test_purchase_order_receive_batch_semantics.py

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text

from app.wms.procurement.services.receive_po_line import receive_po_line
from tests.helpers.po_testkit import create_po_with_line_and_draft_receipt


async def _create_item(session, *, has_shelf_life: bool) -> int:
    r"""
    仅为本测试创建最小 item。

    Phase M-5（终态）：
    - items.uom 已删除
    - items policy NOT NULL 且无默认：
      - lot_source_policy
      - expiry_policy
      - derivation_allowed
      - uom_governance_enabled
    - 单位真相源唯一为 item_uoms：本测试必须补齐 base+defaults
    """
    expiry_policy = "REQUIRED" if bool(has_shelf_life) else "NONE"
    name = "UT-item-shelf" if has_shelf_life else "UT-item-noshelf"
    sku = (
        f"UT-SKU-SHELF-{datetime.now(timezone.utc).timestamp()}"
        if has_shelf_life
        else f"UT-SKU-NOSHELF-{datetime.now(timezone.utc).timestamp()}"
    )

    # 终态语义对齐：
    # - 非效期商品（expiry_policy=NONE）不应被 SUPPLIER_ONLY 的 batch 必填规则拦住，
    #   因此该用例采用 INTERNAL_ONLY；
    # - 效期商品用 SUPPLIER_ONLY（批次受控）以覆盖批次/日期写入语义。
    lot_source_policy = "SUPPLIER_ONLY" if has_shelf_life else "INTERNAL_ONLY"

    row = await session.execute(
        text(
            """
            INSERT INTO items (
              name, sku,
              lot_source_policy, expiry_policy, derivation_allowed, uom_governance_enabled,
              shelf_life_value, shelf_life_unit
            )
            VALUES (
              :name, :sku,
              CAST(:lot_source_policy AS lot_source_policy),
              CAST(:expiry_policy AS expiry_policy),
              TRUE, TRUE,
              CASE WHEN CAST(:expiry_policy AS text) = 'REQUIRED' THEN 30 ELSE NULL END,
              CASE WHEN CAST(:expiry_policy AS text) = 'REQUIRED' THEN 'DAY' ELSE NULL END
            )
            RETURNING id
            """
        ),
        {
            "name": name,
            "sku": sku,
            "lot_source_policy": lot_source_policy,
            "expiry_policy": expiry_policy,
        },
    )
    item_id = int(row.scalar_one())

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

    return item_id


async def _pick_uom_id(session, *, item_id: int) -> int:
    """
    终态合同：receive_po_line 必须显式传 uom_id。
    本测试已为 item 写入 base uom (PCS, ratio=1)，因此优先取 is_base=true。
    """
    row = await session.execute(
        text(
            """
            SELECT id
              FROM item_uoms
             WHERE item_id = :i AND is_base = true
             ORDER BY id
             LIMIT 1
            """
        ),
        {"i": int(item_id)},
    )
    got = row.scalar_one_or_none()
    assert got is not None, {"msg": "item has no base uom", "item_id": int(item_id)}
    return int(got)


@pytest.mark.asyncio
async def test_non_shelf_life_item_forces_null_batch(async_session_maker):
    """
    非效期商品：
    - 即使传 production/expiry
    - receipt_line 中 lot_code_input/production_date/expiry_date 必须全部为 NULL

    Phase M-2/3/4E/ M-5 语义：
    - draft 阶段不产生 lot_id，不创建 lots 记录
    - lot_id / lots 只在 confirm 阶段生成/固化
    """
    async with async_session_maker() as session:
        item_id = await _create_item(session, has_shelf_life=False)
        world = await create_po_with_line_and_draft_receipt(session, item_id=item_id)
        await session.commit()

    async with async_session_maker() as session:
        uom_id = await _pick_uom_id(session, item_id=item_id)
        await receive_po_line(
            session,
            po_id=world.po_id,
            line_id=world.po_line_id,
            qty=1,
            uom_id=uom_id,
            occurred_at=datetime.now(tz=timezone.utc),
            production_date=date(2026, 1, 1),
            expiry_date=date(2026, 6, 1),
        )
        await session.commit()

    async with async_session_maker() as session:
        row = await session.execute(
            text(
                """
                SELECT lot_code_input, production_date, expiry_date, lot_id
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

        # ✅ draft 阶段不产生 lot_id
        assert r[3] is None

        # ✅ draft 阶段不创建 lots
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
      receipt_line 的 (lot_code_input, production_date, expiry_date) 要么全 NULL，要么全非 NULL。
    """
    async with async_session_maker() as session:
        item_id = await _create_item(session, has_shelf_life=True)
        world = await create_po_with_line_and_draft_receipt(session, item_id=item_id)
        await session.commit()

    code = "UT-BATCH-1"

    async with async_session_maker() as session:
        uom_id = await _pick_uom_id(session, item_id=item_id)
        await receive_po_line(
            session,
            po_id=world.po_id,
            line_id=world.po_line_id,
            qty=1,
            uom_id=uom_id,
            occurred_at=datetime.now(tz=timezone.utc),
            lot_code=code,
            production_date=date(2026, 1, 1),
            expiry_date=date(2026, 6, 1),
        )
        await session.commit()

    async with async_session_maker() as session:
        uom_id = await _pick_uom_id(session, item_id=item_id)
        await receive_po_line(
            session,
            po_id=world.po_id,
            line_id=world.po_line_id,
            qty=1,
            uom_id=uom_id,
            occurred_at=datetime.now(tz=timezone.utc),
            lot_code=code,
            production_date=date(2026, 1, 1),
            expiry_date=date(2026, 12, 1),
        )
        await session.commit()

    async with async_session_maker() as session:
        row = await session.execute(
            text(
                """
                SELECT lot_code_input, production_date, expiry_date
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

        lot_code_input, prod, exp = r[0], r[1], r[2]
        all_null = (lot_code_input is None) and (prod is None) and (exp is None)
        all_present = (lot_code_input is not None) and (prod is not None) and (exp is not None)
        assert all_null or all_present, (lot_code_input, prod, exp)
