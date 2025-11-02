from datetime import date

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.grp_scan


async def _has_col(session, table, col) -> bool:
    sql = text(
        """
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema='public'
        AND table_name=:t
        AND column_name=:c
    """
    )
    return (await session.execute(sql, {"t": table, "c": col})).first() is not None


@pytest.mark.asyncio
async def test_batches_expiry_check_and_trigger(session):
    # 1) 前置：确认三列存在，否则跳过（兼容不同环境的 batches 结构）
    need_cols = ["production_date", "shelf_life_days", "expire_at"]
    if not all([await _has_col(session, "batches", c) for c in need_cols]):
        pytest.skip("batches missing expiry-related columns; skip DB expiry test")

    # 2) 使用现有实体，避免外键违例；若无数据，同样跳过
    row_item = (await session.execute(text("SELECT id FROM items LIMIT 1"))).first()
    row_loc = (
        await session.execute(text("SELECT id, warehouse_id FROM locations LIMIT 1"))
    ).first()
    if not row_item or not row_loc:
        pytest.skip("items/locations are empty in this environment; skip DB expiry test")

    item_id = row_item[0]
    location_id, warehouse_id = row_loc[0], row_loc[1]

    # 3) 触发器兜底：不给 expire_at，但给 production_date + shelf_life_days
    sql_ins = text(
        """
      INSERT INTO batches (item_id, warehouse_id, location_id, batch_code, production_date, shelf_life_days)
      VALUES (:item_id, :wh, :loc, 'AUTO-EXP-TEST', :pd, :days)
      RETURNING id, expire_at
    """
    )
    row = (
        await session.execute(
            sql_ins,
            {
                "item_id": item_id,
                "wh": warehouse_id,
                "loc": location_id,
                "pd": date(2025, 10, 31),
                "days": 10,
            },
        )
    ).first()
    assert row is not None, "insert should return a row"
    _, expire_at = row
    assert expire_at is not None, "trigger should fill expire_at when pd & days provided"
    assert expire_at == date(
        2025, 11, 10
    ), "expire_at should equal production_date + shelf_life_days"

    # 4) CHECK 约束：当 pd/expire_at 并存，expire_at 必须 >= production_date
    sql_bad = text(
        """
      INSERT INTO batches (item_id, warehouse_id, location_id, batch_code, production_date, shelf_life_days, expire_at)
      VALUES (:item_id, :wh, :loc, 'AUTO-EXP-BAD', :pd, 1, :exp)
    """
    )
    with pytest.raises(Exception):
        await session.execute(
            sql_bad,
            {
                "item_id": item_id,
                "wh": warehouse_id,
                "loc": location_id,
                "pd": date(2025, 11, 2),
                "exp": date(2025, 11, 1),
            },
        )
