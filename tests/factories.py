# tests/factories.py
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


def get_stock(
    db: Session,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code: Optional[str] = None,
) -> dict[str, Any]:
    """
    Phase M-5: legacy stocks 表已物理删除；统一以 stocks_lot 作为库存余额真相源。

    语义：
    - batch_code=None：NULL 槽位（lot_id IS NULL）
    - batch_code=str ：将 batch_code 视为 lot_code（展示码），通过 lots 解析到 lot_id
    """
    if batch_code is None:
        row = db.execute(
            text(
                """
                SELECT
                  sl.warehouse_id,
                  sl.item_id,
                  NULL::text AS batch_code,
                  sl.lot_id,
                  sl.qty
                FROM stocks_lot sl
                WHERE sl.warehouse_id = :w
                  AND sl.item_id = :i
                  AND sl.lot_id IS NULL
                LIMIT 1
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id)},
        ).mappings().first()
        return dict(row) if row else {"warehouse_id": warehouse_id, "item_id": item_id, "batch_code": None, "lot_id": None, "qty": 0}

    code = str(batch_code).strip()
    row2 = db.execute(
        text(
            """
            SELECT
              sl.warehouse_id,
              sl.item_id,
              l.lot_code AS batch_code,
              sl.lot_id,
              sl.qty
            FROM stocks_lot sl
            JOIN lots l ON l.id = sl.lot_id
            WHERE sl.warehouse_id = :w
              AND sl.item_id = :i
              AND l.lot_code = :c
            LIMIT 1
            """
        ),
        {"w": int(warehouse_id), "i": int(item_id), "c": code},
    ).mappings().first()
    return dict(row2) if row2 else {"warehouse_id": warehouse_id, "item_id": item_id, "batch_code": code, "lot_id": None, "qty": 0}
