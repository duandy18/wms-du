"""items_supplier_id_not_null_and_fk_restrict

Revision ID: 64ae43b2e55c
Revises: 7c1063ea1d78
Create Date: 2025-12-13 10:49:50.543277

目标（Phase 3 延展）：
- items.supplier_id 必须非空（新建即完整）
- 修复 fk_items_supplier：ON DELETE SET NULL -> ON DELETE RESTRICT（禁止删供应商导致商品变“无主”）
- 对历史 supplier_id 为 NULL 的 items 做一次性回填：绑定占位供应商 SUP-UNKNOWN
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "64ae43b2e55c"
down_revision: Union[str, Sequence[str], None] = "7c1063ea1d78"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) 确保占位供应商存在（幂等）
    #    注意：suppliers.code 已在上一迁移中变为 NOT NULL 且 UNIQUE
    op.execute(
        sa.text(
            """
            INSERT INTO suppliers (name, code, active)
            VALUES ('UNKNOWN SUPPLIER', 'SUP-UNKNOWN', TRUE)
            ON CONFLICT (code) DO NOTHING;
            """
        )
    )

    # 2) 取占位 supplier_id
    bind = op.get_bind()
    unknown_id = bind.execute(
        sa.text("SELECT id FROM suppliers WHERE code = 'SUP-UNKNOWN' LIMIT 1;")
    ).scalar_one()

    # 3) 回填历史 items.supplier_id NULL
    op.execute(
        sa.text(
            """
            UPDATE items
               SET supplier_id = :sid
             WHERE supplier_id IS NULL;
            """
        ).bindparams(sa.bindparam("sid", unknown_id))
    )

    # 4) 先改列为 NOT NULL（回填后再加硬约束）
    op.alter_column(
        "items",
        "supplier_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    # 5) 重建外键：SET NULL -> RESTRICT
    #    约束名来自你当前 DB：fk_items_supplier
    op.drop_constraint("fk_items_supplier", "items", type_="foreignkey")
    op.create_foreign_key(
        "fk_items_supplier",
        "items",
        "suppliers",
        ["supplier_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    # 回滚：把 FK 改回 SET NULL，列放回可空
    op.drop_constraint("fk_items_supplier", "items", type_="foreignkey")
    op.create_foreign_key(
        "fk_items_supplier",
        "items",
        "suppliers",
        ["supplier_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.alter_column(
        "items",
        "supplier_id",
        existing_type=sa.Integer(),
        nullable=True,
    )

    # 不删除 SUP-UNKNOWN：避免数据不可解释 / 回滚造成丢失风险
