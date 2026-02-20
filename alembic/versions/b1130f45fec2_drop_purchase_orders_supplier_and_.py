"""drop purchase_orders.supplier and enforce supplier_id+supplier_name

Revision ID: b1130f45fec2
Revises: 101453ae639d
Create Date: 2026-02-20 11:06:14.557649

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1130f45fec2"
down_revision: Union[str, Sequence[str], None] = "101453ae639d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    目标：
    1) 用 supplier_name 补齐旧 supplier 文本
    2) 回填 supplier_id（基于 suppliers.name 精确匹配）
    3) 强制 supplier_id / supplier_name NOT NULL
    4) 同步列注释（避免 alembic-check comment drift）
    5) 建立 FK
    6) 删除 purchase_orders.supplier 列 + 索引
    """

    # 1) supplier_name 补齐：优先已有 supplier_name，否则用旧 supplier 文本
    op.execute(
        """
        UPDATE purchase_orders
        SET supplier_name = COALESCE(supplier_name, supplier)
        WHERE supplier_name IS NULL
        """
    )

    # 2) 回填 supplier_id：用 suppliers.name 精确匹配 supplier_name
    op.execute(
        """
        UPDATE purchase_orders po
        SET supplier_id = s.id
        FROM suppliers s
        WHERE po.supplier_id IS NULL
          AND po.supplier_name = s.name
        """
    )

    # 3) 若仍有 supplier_id 为空 -> 阻断迁移（必须先治理历史数据）
    op.execute(
        """
        DO $$
        DECLARE
            v_cnt bigint;
        BEGIN
            SELECT COUNT(*) INTO v_cnt
            FROM purchase_orders
            WHERE supplier_id IS NULL;
            IF v_cnt > 0 THEN
                RAISE EXCEPTION
                    'purchase_orders.supplier_id still NULL for % rows; please fix supplier mapping before migration',
                    v_cnt;
            END IF;
        END$$;
        """
    )

    # 4) 收紧 NOT NULL
    op.alter_column(
        "purchase_orders",
        "supplier_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "purchase_orders",
        "supplier_name",
        existing_type=sa.String(length=255),
        nullable=False,
    )

    # 4.5) 同步列注释（否则 alembic-check 会检测到 comment drift）
    op.alter_column(
        "purchase_orders",
        "supplier_id",
        existing_type=sa.Integer(),
        comment="FK → suppliers.id（必填）",
    )
    op.alter_column(
        "purchase_orders",
        "supplier_name",
        existing_type=sa.String(length=255),
        comment="下单时的供应商名称快照（必填，通常来自 suppliers.name）",
    )

    # 5) 建立 FK（如果你库里已存在同名约束，会在这里冲突；到时改名或先 drop）
    op.create_foreign_key(
        "fk_purchase_orders_supplier_id",
        "purchase_orders",
        "suppliers",
        ["supplier_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # 6) 删除旧 supplier 文本索引（如果存在）
    try:
        op.drop_index("ix_purchase_orders_supplier", table_name="purchase_orders")
    except Exception:
        pass

    # 7) 删除旧 supplier 文本列
    op.drop_column("purchase_orders", "supplier")


def downgrade() -> None:
    """
    回滚逻辑：
    1) 恢复 supplier 列 + 索引
    2) 用 supplier_name 回填 supplier
    3) 回滚列注释
    4) 放开 NOT NULL
    5) 删除 FK
    """

    # 1) 恢复 supplier 列
    op.add_column(
        "purchase_orders",
        sa.Column("supplier", sa.String(length=100), nullable=False, server_default=""),
    )
    op.create_index("ix_purchase_orders_supplier", "purchase_orders", ["supplier"])

    # 2) 用 supplier_name 回填 supplier（避免空）
    op.execute(
        """
        UPDATE purchase_orders
        SET supplier = COALESCE(supplier_name, '')
        """
    )

    # 3) 回滚列注释（与旧 ORM/DB 口径一致）
    op.alter_column(
        "purchase_orders",
        "supplier_id",
        existing_type=sa.Integer(),
        comment="FK → suppliers.id，可为空",
    )
    op.alter_column(
        "purchase_orders",
        "supplier_name",
        existing_type=sa.String(length=255),
        comment="下单时的供应商名称快照，通常来自 suppliers.name",
    )

    # 4) 放开 NOT NULL（回滚时不强求）
    op.alter_column(
        "purchase_orders",
        "supplier_name",
        existing_type=sa.String(length=255),
        nullable=True,
    )
    op.alter_column(
        "purchase_orders",
        "supplier_id",
        existing_type=sa.Integer(),
        nullable=True,
    )

    # 5) 删除 FK
    op.drop_constraint(
        "fk_purchase_orders_supplier_id",
        "purchase_orders",
        type_="foreignkey",
    )
