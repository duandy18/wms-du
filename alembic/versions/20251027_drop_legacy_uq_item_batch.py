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
LEGACY_UQ_NAME = "uq_batches_item_batch"  # 常见旧名，仍做列集合兜底


def _find_constraints_on_cols(conn, table: str, cols: List[str]) -> List[str]:
    """
    返回表上“恰好覆盖 cols 这组列”的唯一约束名列表。
    注意：不能写 unnest(:cols::text[])；须在 SQL 内构造数组字面量，
    同时列名作为标量参数绑定，避免 SQL 注入与语法错误。
    """
    # 组装 ARRAY[:c0,:c1,...]::text[]
    arr_params = {f"c{i}": col for i, col in enumerate(cols)}
    arr_literal = "ARRAY[" + ",".join([f":c{i}" for i in range(len(cols))]) + "]::text[]"

    sql = sa.text(
        f"""
        SELECT c.conname
          FROM pg_constraint c
          JOIN pg_class t ON t.oid = c.conrelid
         WHERE t.relname = :table
           AND c.contype = 'u'
           AND (
                SELECT ARRAY_AGG(att.attname ORDER BY att.attname)
                  FROM unnest(c.conkey) AS key(attnum)
                  JOIN pg_attribute att
                    ON att.attrelid = c.conrelid AND att.attnum = key.attnum
               ) = (
                SELECT ARRAY_AGG(col ORDER BY col)
                  FROM unnest({arr_literal}) AS s(col)
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
