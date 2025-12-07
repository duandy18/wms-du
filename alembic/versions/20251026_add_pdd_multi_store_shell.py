"""PDD multi-store shell: create stores / store_items / channel_inventory

Revision ID: 20251026_add_pdd_multi_store_shell
Revises: 8cc9988c7301
Create Date: 2025-10-26 12:30:00

蓝图依据：
- stores: id, name, platform='pdd', api_token(enc), active BOOL, created_at, updated_at
- store_items: id, store_id(FK), item_id(FK), pdd_sku_id, outer_id; UNIQUE (store_id, pdd_sku_id) & (store_id, item_id)
- channel_inventory: id, store_id, item_id, cap_qty NULL, reserved_qty INT DEFAULT 0, visible_qty INT DEFAULT 0; UNIQUE (store_id, item_id)
- FK: ON DELETE RESTRICT
- 时区：业务日 Asia/Shanghai(UTC+8)，存储统一 UTC（timestamptz）
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251026_add_pdd_multi_store_shell"
down_revision = "8cc9988c7301"  # 若不匹配你本地当前 head，请改成实际的 head
branch_labels = None
depends_on = None


def upgrade():
    # 兼容 PG/SQLite 的时间默认值
    created_default = sa.text("CURRENT_TIMESTAMP")
    updated_default = sa.text("CURRENT_TIMESTAMP")

    # == stores ==
    op.create_table(
        "stores",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False, server_default="pdd"),
        # api_token：v1 先用 TEXT/BYTEA 承载；后续可接 KMS/加密方案
        sa.Column("api_token", sa.LargeBinary, nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("TRUE")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=created_default
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=updated_default
        ),
    )
    op.create_index("ix_stores_platform_name", "stores", ["platform", "name"], unique=False)

    # == store_items ==
    op.create_table(
        "store_items",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("store_id", sa.Integer, nullable=False),
        sa.Column("item_id", sa.Integer, nullable=False),
        sa.Column("pdd_sku_id", sa.String(length=64), nullable=True),
        sa.Column("outer_id", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("store_id", "pdd_sku_id", name="uq_store_items_store_pddsku"),
        sa.UniqueConstraint("store_id", "item_id", name="uq_store_items_store_item"),
    )
    op.create_index("ix_store_items_store", "store_items", ["store_id"], unique=False)
    op.create_index("ix_store_items_item", "store_items", ["item_id"], unique=False)
    op.create_index("ix_store_items_pdd_sku_id", "store_items", ["pdd_sku_id"], unique=False)

    # == channel_inventory ==
    op.create_table(
        "channel_inventory",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("store_id", sa.Integer, nullable=False),
        sa.Column("item_id", sa.Integer, nullable=False),
        sa.Column("cap_qty", sa.Integer, nullable=True),  # NULL 代表无限上限
        sa.Column("reserved_qty", sa.Integer, nullable=False, server_default="0"),
        sa.Column("visible_qty", sa.Integer, nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("store_id", "item_id", name="uq_channel_inventory_store_item"),
    )
    op.create_index("ix_channel_inventory_store", "channel_inventory", ["store_id"], unique=False)
    op.create_index("ix_channel_inventory_item", "channel_inventory", ["item_id"], unique=False)

    # == PG 专属：touch updated_at 触发器（可重复使用） ==
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION touch_updated_at()
            RETURNS TRIGGER AS $$
            BEGIN
              NEW.updated_at = NOW();
              RETURN NEW;
            END
            $$ LANGUAGE plpgsql;
            """
        )
        # 注意：只有 stores / 将来可能扩到 store_items（若频繁更新）
        op.execute(
            """
            DROP TRIGGER IF EXISTS trg_stores_touch ON stores;
            CREATE TRIGGER trg_stores_touch
            BEFORE UPDATE ON stores
            FOR EACH ROW EXECUTE PROCEDURE touch_updated_at();
            """
        )

    # == 非负约束（PG 有效，SQLite 忽略 CHECK 或以软件层保证） ==
    with op.batch_alter_table("channel_inventory") as b:
        b.create_check_constraint("ck_channel_inventory_reserved_nonneg", "reserved_qty >= 0")
        b.create_check_constraint("ck_channel_inventory_visible_nonneg", "visible_qty >= 0")
    with op.batch_alter_table("store_items") as b:
        # 允许 pdd_sku_id 为 NULL；如果不为 NULL，则去重由 UQ 保证
        pass


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_stores_touch ON stores;")
        op.execute("DROP FUNCTION IF EXISTS touch_updated_at();")

    op.drop_index("ix_channel_inventory_item", table_name="channel_inventory")
    op.drop_index("ix_channel_inventory_store", table_name="channel_inventory")
    op.drop_table("channel_inventory")

    op.drop_index("ix_store_items_pdd_sku_id", table_name="store_items")
    op.drop_index("ix_store_items_item", table_name="store_items")
    op.drop_index("ix_store_items_store", table_name="store_items")
    op.drop_table("store_items")

    op.drop_index("ix_stores_platform_name", table_name="stores")
    op.drop_table("stores")
