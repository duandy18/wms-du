# tests/services/test_internal_outbound_service.py
import pytest
from datetime import date, timedelta

from sqlalchemy import text

from app.db.session import async_session_maker
from app.wms.stock.services.lots import ensure_lot_full
from app.wms.stock.services.stock_service import StockService
from app.wms.outbound.services.internal_outbound.service import InternalOutboundService
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
    """

    warehouse_id = 1
    item_id = 1
    qty_seed = 10
    qty_outbound = 4
    batch_code = "INT-SEED-TEST-001"

    # STEP 0 — 清理现场
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
                          AND lot_code = :code
                   )
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "code": str(batch_code)},
        )

        await session.execute(
            text(
                """
                DELETE FROM lots
                 WHERE warehouse_id = :w
                   AND item_id      = :i
                   AND lot_code_source = 'SUPPLIER'
                   AND lot_code = :code
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "code": str(batch_code)},
        )

        await session.commit()

    # STEP 1 — 种子库存 +10
    async with async_session_maker() as session:
        await ensure_warehouse(session, id=int(warehouse_id), name="WH-1")
        await ensure_item(session, id=int(item_id), sku=f"SKU-{item_id}", name=f"ITEM-{item_id}")

        await session.execute(
            text("UPDATE items SET expiry_policy='REQUIRED'::expiry_policy WHERE id=:i"),
            {"i": int(item_id)},
        )

        await session.commit()

        prod = date.today()
        exp = prod + timedelta(days=365)

        lot_id = await ensure_lot_full(
            session,
            item_id=int(item_id),
            warehouse_id=int(warehouse_id),
            lot_code=str(batch_code),
            production_date=prod,
            expiry_date=exp,
        )

        stock_svc = StockService()
        res = await stock_svc.adjust_lot(
            session=session,
            item_id=item_id,
            warehouse_id=warehouse_id,
            lot_id=int(lot_id),
            delta=qty_seed,
            reason="TEST_SEED",
            ref="INT-SEED-TEST-001",
            ref_line=1,
            batch_code=batch_code,
            production_date=prod,
            expiry_date=exp,
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

    # STEP 3 — 添加一行 qty=4
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
                       AND l.lot_code = :code
                    """
                ),
                {"w": int(warehouse_id), "i": int(item_id), "code": str(batch_code)},
            )
        ).scalar()

        assert int(stock or 0) == qty_seed - qty_outbound

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
