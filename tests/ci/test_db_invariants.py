# tests/ci/test_db_invariants.py
import os
from sqlalchemy import create_engine, text


def test_ledger_trigger_fills_item_id():
    """
    目的：验证最小插入台账时（仅 stock_id, delta），DB 层触发器/默认值能补齐：
      - item_id：从 stocks 回填
      - reason：默认 'ADJUST'
      - occurred_at：默认 NOW()
      - after_qty：stocks.qty + delta
      - ref_line：默认 1
    该用例做成幂等：先清理残留，再用 UPSERT 插入 stocks。
    """
    eng = create_engine(os.environ["DATABASE_URL"])

    with eng.begin() as conn:
        # 幂等清理：删除之前这对 (item_id, location_id) 的 ledger 和 stocks 残留
        conn.execute(text("""
            DELETE FROM stock_ledger
            WHERE stock_id IN (
                SELECT id FROM stocks WHERE item_id = 1001 AND location_id = 2001
            )
        """))

        # 使用 UPSERT 写入 stocks（多次运行不会冲突）
        r = conn.execute(text("""
            INSERT INTO stocks (item_id, location_id, qty)
            VALUES (1001, 2001, 0)
            ON CONFLICT (item_id, location_id)
            DO UPDATE SET qty = EXCLUDED.qty
            RETURNING id, item_id
        """))
        stock_id, item_id = r.first()

        # 最小插入台账，只给 stock_id & delta，期望 DB 侧触发器/默认值补齐其它列
        r2 = conn.execute(text("""
            INSERT INTO stock_ledger (stock_id, delta)
            VALUES (:sid, 5)
            RETURNING id, item_id, delta, reason, after_qty, occurred_at, ref_line
        """), {"sid": stock_id})
        ledger_id, filled_item_id, delta, reason, after_qty, occurred_at, ref_line = r2.first()

        # 断言：item_id 回填成功
        assert filled_item_id == 1001
        # 断言：默认/回填字段都存在
        assert reason == 'ADJUST'
        assert after_qty == 5
        assert ref_line == 1
        assert occurred_at is not None
