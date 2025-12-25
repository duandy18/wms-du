"""auto

Revision ID: f7954e3232b5
Revises: 4ec12f14eb40
Create Date: 2025-12-20 18:26:39.386743

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f7954e3232b5"
down_revision: Union[str, Sequence[str], None] = "4ec12f14eb40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---- constraint names (avoid None) ----
FK_ITEMS_SUPPLIER_ID = "fk_items_supplier_id_suppliers"
FK_STORE_WAREHOUSE_WAREHOUSE_ID = "fk_store_warehouse_warehouse_id"
FK_STORE_WAREHOUSE_STORE_ID = "fk_store_warehouse_store_id"
UQ_WAREHOUSES_NAME = "uq_warehouses_name"


def _pg_constraint_exists(table: str, conname: str) -> bool:
    """
    PostgreSQL: 判断约束是否存在（避免 DuplicateObject/DuplicateTable）
    """
    conn = op.get_bind()
    row = conn.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            WHERE t.relname = :table
              AND c.conname = :conname
            LIMIT 1
            """
        ),
        {"table": table, "conname": conname},
    ).first()
    return row is not None


def _pg_index_exists(indexname: str) -> bool:
    """
    PostgreSQL: 判断 index(relkind='i') 是否存在。
    说明：在 PG 里 index 也是 relation，所以 DuplicateTable 常见于 index 同名冲突。
    """
    conn = op.get_bind()
    row = conn.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_class
            WHERE relkind = 'i'
              AND relname = :idx
            LIMIT 1
            """
        ),
        {"idx": indexname},
    ).first()
    return row is not None


def upgrade() -> None:
    """Upgrade schema."""
    # items.has_shelf_life comment
    op.alter_column(
        "items",
        "has_shelf_life",
        existing_type=sa.BOOLEAN(),
        comment="是否需要有效期管理（入库是否强制日期）",
        existing_nullable=False,
        existing_server_default=sa.text("false"),
    )

    # items.supplier_id -> nullable + FK
    op.alter_column(
        "items",
        "supplier_id",
        existing_type=sa.INTEGER(),
        nullable=True,
    )
    if not _pg_constraint_exists("items", FK_ITEMS_SUPPLIER_ID):
        op.create_foreign_key(
            FK_ITEMS_SUPPLIER_ID,
            "items",
            "suppliers",
            ["supplier_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # purchase_orders comments
    op.alter_column(
        "purchase_orders",
        "purchaser",
        existing_type=sa.VARCHAR(length=64),
        comment="采购人姓名或编码",
        existing_nullable=False,
    )
    op.alter_column(
        "purchase_orders",
        "purchase_time",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        comment="采购单创建/确认时间",
        existing_nullable=False,
    )
    op.alter_column(
        "purchase_orders",
        "remark",
        existing_type=sa.VARCHAR(length=255),
        comment="采购单头部备注（可选）",
        existing_comment="采购单头部备注",
        existing_nullable=True,
    )

    # shipping_provider_contacts.role comment -> None（按模型口径）
    op.alter_column(
        "shipping_provider_contacts",
        "role",
        existing_type=sa.VARCHAR(length=32),
        comment=None,
        existing_comment="shipping / billing / after_sales / other",
        existing_nullable=False,
        existing_server_default=sa.text("'other'::character varying"),
    )

    # store_warehouse foreign keys
    if not _pg_constraint_exists("store_warehouse", FK_STORE_WAREHOUSE_WAREHOUSE_ID):
        op.create_foreign_key(
            FK_STORE_WAREHOUSE_WAREHOUSE_ID,
            "store_warehouse",
            "warehouses",
            ["warehouse_id"],
            ["id"],
            ondelete="CASCADE",
        )
    if not _pg_constraint_exists("store_warehouse", FK_STORE_WAREHOUSE_STORE_ID):
        op.create_foreign_key(
            FK_STORE_WAREHOUSE_STORE_ID,
            "store_warehouse",
            "stores",
            ["store_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # supplier_contacts.role comment -> None（按模型口径）
    op.alter_column(
        "supplier_contacts",
        "role",
        existing_type=sa.VARCHAR(length=32),
        comment=None,
        existing_comment="采购/对账/发货/售后/其他",
        existing_nullable=False,
        existing_server_default=sa.text("'other'::character varying"),
    )

    # warehouses.code nullable
    op.alter_column(
        "warehouses",
        "code",
        existing_type=sa.VARCHAR(length=64),
        nullable=True,
    )

    # warehouses.name unique
    # 现状（你已确认）：已存在同名 unique index uq_warehouses_name，但 constraint 不存在。
    # 所以优先使用 USING INDEX 升格为 constraint，避免 DuplicateTable。
    if not _pg_constraint_exists("warehouses", UQ_WAREHOUSES_NAME):
        if _pg_index_exists(UQ_WAREHOUSES_NAME):
            op.execute(
                sa.text(
                    f"ALTER TABLE warehouses "
                    f"ADD CONSTRAINT {UQ_WAREHOUSES_NAME} UNIQUE USING INDEX {UQ_WAREHOUSES_NAME}"
                )
            )
        else:
            op.create_unique_constraint(UQ_WAREHOUSES_NAME, "warehouses", ["name"])


def downgrade() -> None:
    """Downgrade schema."""
    # warehouses.name unique（若 constraint 存在则删；注意：drop_constraint 不会自动删除 index）
    if _pg_constraint_exists("warehouses", UQ_WAREHOUSES_NAME):
        op.drop_constraint(UQ_WAREHOUSES_NAME, "warehouses", type_="unique")

    # warehouses.code back to not null
    op.alter_column(
        "warehouses",
        "code",
        existing_type=sa.VARCHAR(length=64),
        nullable=False,
    )

    # supplier_contacts.role comment restore
    op.alter_column(
        "supplier_contacts",
        "role",
        existing_type=sa.VARCHAR(length=32),
        comment="采购/对账/发货/售后/其他",
        existing_nullable=False,
        existing_server_default=sa.text("'other'::character varying"),
    )

    # drop store_warehouse FKs (若不存在则跳过)
    if _pg_constraint_exists("store_warehouse", FK_STORE_WAREHOUSE_STORE_ID):
        op.drop_constraint(FK_STORE_WAREHOUSE_STORE_ID, "store_warehouse", type_="foreignkey")
    if _pg_constraint_exists("store_warehouse", FK_STORE_WAREHOUSE_WAREHOUSE_ID):
        op.drop_constraint(FK_STORE_WAREHOUSE_WAREHOUSE_ID, "store_warehouse", type_="foreignkey")

    # shipping_provider_contacts.role comment restore
    op.alter_column(
        "shipping_provider_contacts",
        "role",
        existing_type=sa.VARCHAR(length=32),
        comment="shipping / billing / after_sales / other",
        existing_nullable=False,
        existing_server_default=sa.text("'other'::character varying"),
    )

    # purchase_orders comments restore
    op.alter_column(
        "purchase_orders",
        "remark",
        existing_type=sa.VARCHAR(length=255),
        comment="采购单头部备注",
        existing_comment="采购单头部备注（可选）",
        existing_nullable=True,
    )
    op.alter_column(
        "purchase_orders",
        "purchase_time",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        comment=None,
        existing_comment="采购单创建/确认时间",
        existing_nullable=False,
    )
    op.alter_column(
        "purchase_orders",
        "purchaser",
        existing_type=sa.VARCHAR(length=64),
        comment=None,
        existing_comment="采购人姓名或编码",
        existing_nullable=False,
    )

    # drop items FK and revert nullable (若 FK 不存在则跳过)
    if _pg_constraint_exists("items", FK_ITEMS_SUPPLIER_ID):
        op.drop_constraint(FK_ITEMS_SUPPLIER_ID, "items", type_="foreignkey")
    op.alter_column(
        "items",
        "supplier_id",
        existing_type=sa.INTEGER(),
        nullable=False,
    )

    # items.has_shelf_life comment restore
    op.alter_column(
        "items",
        "has_shelf_life",
        existing_type=sa.BOOLEAN(),
        comment=None,
        existing_comment="是否需要有效期管理（入库是否强制日期）",
        existing_nullable=False,
        existing_server_default=sa.text("false"),
    )
