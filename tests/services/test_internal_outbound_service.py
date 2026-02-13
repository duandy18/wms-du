# tests/services/test_internal_outbound_service.py
import pytest
from datetime import date
from sqlalchemy import text

from app.db.session import async_session_maker
from app.services.stock_service import StockService
from app.services.internal_outbound_service import InternalOutboundService


@pytest.mark.asyncio
async def test_internal_outbound_end_to_end():
    """
    内部出库完整链路测试：
      1) 种子：给 item_id=1, wh=1 种 10 个库存（特定批次）
      2) 创建内部出库单（SAMPLE_OUT，领取人=张三）
      3) 添加一行 item_id=1, qty=4，指定同一批次
      4) 确认内部出库（扣库存）
      5) 验证：对该批次的 stocks 减少 / ledger 写入 INTERNAL_OUT 记录
    """

    warehouse_id = 1
    item_id = 1
    qty_seed = 10
    qty_outbound = 4
    batch_code = "INT-SEED-TEST-001"

    # STEP 0 — 清理现场：删除旧的 seed 测试库存（可选）
    async with async_session_maker() as session:
        await session.execute(
            text("DELETE FROM stock_ledger WHERE scope='PROD' AND ref = 'INT-SEED-TEST-001'")
        )
        await session.execute(
            text(
                "DELETE FROM stocks WHERE scope='PROD' AND warehouse_id=:w AND item_id=:i AND batch_code=:c"
            ),
            {"w": warehouse_id, "i": item_id, "c": batch_code},
        )
        await session.commit()

    # STEP 1 — 种子库存 +10（特定批次）
    async with async_session_maker() as session:
        stock_svc = StockService()
        res = await stock_svc.adjust(
            session=session,
            scope="PROD",
            item_id=item_id,
            warehouse_id=warehouse_id,
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
        assert res["after"] == qty_seed

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

    # STEP 3 — 添加一行 qty=4，显式指定和种子相同的批次
    async with async_session_maker() as session:
        svc = InternalOutboundService()
        await svc.upsert_line(
            session,
            doc_id=doc_id,
            item_id=item_id,
            qty=qty_outbound,
            batch_code=batch_code,  # ✅ 指定批次，避免 FEFO 跑到别的历史批次
            uom="PCS",
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
                    SELECT qty
                      FROM stocks
                     WHERE scope='PROD'
                       AND warehouse_id=:w AND item_id=:i AND batch_code=:c
                     ORDER BY qty DESC LIMIT 1
                    """
                ),
                {"w": warehouse_id, "i": item_id, "c": batch_code},
            )
        ).scalar()
        assert stock == qty_seed - qty_outbound  # 10 - 4 = 6

        ledger_rows = (
            await session.execute(
                text(
                    """
                    SELECT reason, delta
                      FROM stock_ledger
                     WHERE scope='PROD'
                       AND ref = :ref
                     ORDER BY id DESC
                     LIMIT 10
                    """
                ),
                {"ref": doc3.doc_no},
            )
        ).all()

        assert len(ledger_rows) >= 1
        assert any(r[0] == "INTERNAL_OUT" and r[1] < 0 for r in ledger_rows)
