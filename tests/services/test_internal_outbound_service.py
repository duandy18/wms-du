# tests/services/test_internal_outbound_service.py
import pytest
from datetime import date

from sqlalchemy import text

from app.db.session import async_session_maker
from app.services.stock_service import StockService
from app.services.internal_outbound_service import InternalOutboundService
from tests.utils.ensure_minimal import ensure_item, ensure_warehouse


@pytest.mark.asyncio
async def test_internal_outbound_end_to_end():
    """
    内部出库完整链路测试（Phase 4D / lot-world）：
      1) 种子：给 item_id=1, wh=1 种 10 个库存（SUPPLIER lot_code）
      2) 创建内部出库单（SAMPLE_OUT，领取人=张三）
      3) 添加一行 item_id=1, qty=4，指定同一 lot_code（batch_code 展示码）
      4) 确认内部出库（扣 stocks_lot）
      5) 验证：stocks_lot 减少 / ledger 写入 INTERNAL_OUT 记录

    Phase M-3：
      - items.case_ratio/case_uom 已删除；lots 不再承载 item_case_*_snapshot / item_uom_snapshot 等历史残影列
      - lots 也不再承载 production_date/expiry_date/expiry_source（日期事实在 receipt/ledger 侧表达）
    """

    warehouse_id = 1
    item_id = 1
    qty_seed = 10
    qty_outbound = 4
    batch_code = "INT-SEED-TEST-001"  # 作为 SUPPLIER lot_code 使用

    # STEP 0 — 清理现场：删除旧的 seed 测试台账 + lot-world 库存
    async with async_session_maker() as session:
        await session.execute(text("DELETE FROM stock_ledger WHERE ref = 'INT-SEED-TEST-001'"))

        await session.execute(
            text(
                """
                DELETE FROM stocks_lot sl
                 WHERE sl.warehouse_id = :w
                   AND sl.item_id      = :i
                   AND sl.lot_id IN (
                       SELECT id
                         FROM lots
                        WHERE warehouse_id = :w
                          AND item_id      = :i
                          AND lot_code_source = 'SUPPLIER'
                          AND lot_code = :c
                   )
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "c": str(batch_code)},
        )

        await session.execute(
            text(
                """
                DELETE FROM lots
                 WHERE warehouse_id = :w
                   AND item_id      = :i
                   AND lot_code_source = 'SUPPLIER'
                   AND lot_code     = :c
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "c": str(batch_code)},
        )

        await session.commit()

    # STEP 1 — 种子库存 +10（特定 lot_code）
    async with async_session_maker() as session:
        await ensure_warehouse(session, id=int(warehouse_id), name="WH-1")
        await ensure_item(session, id=int(item_id), sku=f"SKU-{item_id}", name=f"ITEM-{item_id}")
        await session.commit()

        # lots 终态：仅结构身份 + 必要快照，不承载 production/expiry 等日期事实列
        # 唯一性：uq_lots_wh_item_lot_code => (warehouse_id,item_id,lot_code) WHERE lot_code IS NOT NULL
        lot_row = (
            await session.execute(
                text(
                    """
                    INSERT INTO lots(
                        warehouse_id,
                        item_id,
                        lot_code_source,
                        lot_code,
                        source_receipt_id,
                        source_line_no,
                        -- required snapshots (NOT NULL)
                        item_lot_source_policy_snapshot,
                        item_expiry_policy_snapshot,
                        item_derivation_allowed_snapshot,
                        item_uom_governance_enabled_snapshot,
                        -- optional snapshots (nullable)
                        item_shelf_life_value_snapshot,
                        item_shelf_life_unit_snapshot,
                        created_at
                    )
                    SELECT
                        :w,
                        it.id,
                        'SUPPLIER',
                        :code,
                        NULL,
                        NULL,
                        it.lot_source_policy,
                        it.expiry_policy,
                        it.derivation_allowed,
                        it.uom_governance_enabled,
                        it.shelf_life_value,
                        it.shelf_life_unit,
                        now()
                      FROM items it
                     WHERE it.id = :i
                    ON CONFLICT (warehouse_id, item_id, lot_code)
                    WHERE lot_code IS NOT NULL
                    DO UPDATE SET lot_code_source = EXCLUDED.lot_code_source
                    RETURNING id
                    """
                ),
                {"w": int(warehouse_id), "i": int(item_id), "code": str(batch_code)},
            )
        ).first()
        assert lot_row is not None, "failed to ensure lot"
        lot_id = int(lot_row[0])

        stock_svc = StockService()
        res = await stock_svc.adjust_lot(
            session=session,
            item_id=item_id,
            warehouse_id=warehouse_id,
            lot_id=lot_id,
            delta=qty_seed,
            reason="TEST_SEED",
            ref="INT-SEED-TEST-001",
            ref_line=1,
            batch_code=batch_code,
            production_date=date.today(),
            expiry_date=None,
            trace_id="INT-SEED-TRACE",
        )
        await session.commit()
        assert int(res["after"]) == qty_seed

    # STEP 2 — 创建内部出库单
    async with async_session_maker() as session:
        svc = InternalOutboundService()
        doc = await svc.create_doc(
            session,
            warehouse_id=warehouse_id,
            doc_type="SAMPLE_OUT",
            recipient_name="张三",
            note="pytest-内部出库",
        )
        await session.commit()

        doc_id = doc.id
        assert doc.status == "DRAFT"
        assert doc.recipient_name == "张三"

    # STEP 3 — 添加一行 qty=4，显式指定和种子相同的 lot_code（batch_code 展示码）
    async with async_session_maker() as session:
        svc = InternalOutboundService()
        await svc.upsert_line(
            session,
            doc_id=doc_id,
            item_id=item_id,
            qty=qty_outbound,
            batch_code=batch_code,
            note="测试行",
        )
        await session.commit()

        doc2 = await svc.get_with_lines(session, doc_id)
        assert len(doc2.lines) == 1
        line = doc2.lines[0]
        assert line.item_id == item_id
        assert line.requested_qty == qty_outbound
        assert line.batch_code == batch_code

    # STEP 4 — 确认内部出库
    async with async_session_maker() as session:
        svc = InternalOutboundService()
        doc3 = await svc.confirm(
            session,
            doc_id=doc_id,
            user_id=None,
        )
        await session.commit()

        assert doc3.status == "CONFIRMED"
        assert doc3.confirmed_at is not None

    # STEP 5 — 验证库存减少与 ledger 存在
    async with async_session_maker() as session:
        stock = (
            await session.execute(
                text(
                    """
                    SELECT COALESCE(SUM(sl.qty), 0)
                      FROM stocks_lot sl
                      JOIN lots l ON l.id = sl.lot_id
                     WHERE sl.warehouse_id = :w
                       AND sl.item_id      = :i
                       AND l.lot_code_source = 'SUPPLIER'
                       AND l.lot_code     = :c
                    """
                ),
                {"w": int(warehouse_id), "i": int(item_id), "c": str(batch_code)},
            )
        ).scalar()

        assert int(stock or 0) == qty_seed - qty_outbound  # 10 - 4 = 6

        ledger_rows = (
            await session.execute(
                text(
                    """
                    SELECT reason, delta
                      FROM stock_ledger
                     WHERE ref = :ref
                     ORDER BY id DESC
                     LIMIT 10
                    """
                ),
                {"ref": doc3.doc_no},
            )
        ).all()

        assert len(ledger_rows) >= 1
        assert any(r[0] == "INTERNAL_OUT" and int(r[1]) < 0 for r in ledger_rows)
