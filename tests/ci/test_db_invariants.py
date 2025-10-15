import os

import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL", "").startswith("postgresql"),
    reason="PG only",
)


def test_ledger_trigger_fills_item_id():
    """验证：插入 stock_ledger 时，触发器能自动填充 item_id。"""
    eng = create_engine(os.environ["DATABASE_URL"])
    with eng.begin() as conn:
        # 1) 先插入一条 stocks（qty 取 0 即可）
        r = conn.execute(
            text(
                """
          INSERT INTO stocks (item_id, location_id, qty)
          VALUES (1001, 2001, 0)
          RETURNING id, item_id
        """
            )
        )
        stock_id, item_id = r.first()

        # 2) 插入 ledger 时不提供 item_id，期望触发器回填
        r2 = conn.execute(
            text(
                """
          INSERT INTO stock_ledger (stock_id, delta)
          VALUES (:sid, 5)
          RETURNING id, item_id, delta
        """
            ),
            {"sid": stock_id},
        )
        _, filled_item_id, delta = r2.first()

        assert filled_item_id == item_id
        assert delta == 5
