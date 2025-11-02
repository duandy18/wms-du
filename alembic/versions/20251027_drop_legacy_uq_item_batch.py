"""drop legacy unique (item_id, batch_code) on batches

Revision ID: 20251027_drop_legacy_uq_item_batch
Revises: 20251027_add_uq_batches_unique
Create Date: 2025-10-27 22:10:00
"""
from __future__ import annotations

from typing import List

from alembic import op
import sqlalchemy as sa

revision = "20251027_drop_legacy_uq_item_batch"
down_revision = "20251027_add_uq_batches_unique"
branch_labels = None
depends_on = None

TABLE = "batches"
LEGACY_UQ_NAME = "uq_batches_item_batch"  # 旧名，仍做列集合兜底


def _literal_text_array(cols: list[str]) -> tuple[str, dict]:
    """
    把 ['a','b'] 变成 ("ARRAY[:c0,:c1]::text[]", {"c0":"a","c1":"b"})
    用于避免 `unnest(:cols::text[])` 的参数化数组语法在 CI 上报错。
    """
    params = {f"c{i}": col for i, col in enumerate(cols)}
    fragment = "ARRAY[" + ",".join([f":c{i}" for i in range(len(cols))]) + "]::text[]"
    return fragment, params


def _find_constraints_on_cols(conn, table: str, cols: List[str]) -> List[str]:
    """
    返回表上“恰好覆盖 cols 这组列”的唯一约束名列表。
    注意：两边数组类型需一致，这里统一转成 text[] 再比较。
    """
    arr_sql, arr_params = _literal_text_array(cols)
    sql = sa.text(
        f"""
        SELECT c.conname
          FROM pg_constraint c
          JOIN pg_class t ON t.oid = c.conrelid
         WHERE t.relname = :table
           AND c.contype = 'u'
           AND (
                SELECT ARRAY_AGG(att.attname::text ORDER BY att.attname::text)
                  FROM unnest(c.conkey) AS key(attnum)
                  JOIN pg_attribute att
                    ON att.attrelid = c.conrelid AND att.attnum = key.attnum
               ) = (
                SELECT ARRAY_AGG(col::text ORDER BY col::text)
                  FROM unnest({arr_sql}) AS s(col)
               )
        """
    )
    params = {"table": table}
    params.update(arr_params)
    rows = conn.execute(sql, params).fetchall()
    return [r[0] for r in rows]


def upgrade() -> None:
    conn = op.get_bind()

    # 1) 优先按约束名删除（若存在）
    sql_name = sa.text(
        """
        SELECT 1
          FROM pg_constraint c
          JOIN pg_class t ON t.oid = c.conrelid
         WHERE t.relname = :t AND c.conname = :n
         LIMIT 1
        """
    )
    if conn.execute(sql_name, {"t": TABLE, "n": LEGACY_UQ_NAME}).scalar():
        op.drop_constraint(LEGACY_UQ_NAME, table_name=TABLE, type_="unique")
        return

    # 2) 兜底：按列集合精确匹配 (item_id, batch_code) 删除历史唯一约束
    for conname in _find_constraints_on_cols(conn, TABLE, ["item_id", "batch_code"]):
        op.drop_constraint(conname, table_name=TABLE, type_="unique")


def downgrade() -> None:
    # 可选：恢复旧唯一约束（通常不需要）
    op.create_unique_constraint(LEGACY_UQ_NAME, TABLE, ["item_id", "batch_code"])
