"""bind_item_barcodes_to_item_uoms

Revision ID: 32b08d41971c
Revises: 4a0e3e897c4f
Create Date: 2026-04-09 16:37:38.385129

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "32b08d41971c"
down_revision: Union[str, Sequence[str], None] = "4a0e3e897c4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1) 先让 item_uoms 具备可被复合外键引用的唯一键
    op.create_unique_constraint(
        "uq_item_uoms_id_item_id",
        "item_uoms",
        ["id", "item_id"],
    )

    # 2) item_barcodes 新增终态字段（先 nullable，回填后再收紧）
    op.add_column(
        "item_barcodes",
        sa.Column("item_uom_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "item_barcodes",
        sa.Column(
            "symbology",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'CUSTOM'"),
            comment="条码码制/来源：EAN13 / EAN8 / UPC / UPC12 / GS1 / CUSTOM ...",
        ),
    )
    op.create_index(
        "ix_item_barcodes_item_uom_id",
        "item_barcodes",
        ["item_uom_id"],
        unique=False,
    )

    # 3) item_barcodes.item_id 类型对齐到 items.id / item_uoms.item_id（integer）
    op.drop_constraint(
        "item_barcodes_item_id_fkey",
        "item_barcodes",
        type_="foreignkey",
    )
    op.alter_column(
        "item_barcodes",
        "item_id",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using="item_id::integer",
    )
    op.create_foreign_key(
        "item_barcodes_item_id_fkey",
        "item_barcodes",
        "items",
        ["item_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 4) symbology 回填：旧 kind 里只有“码制/来源”保留，其它脏语义降级为 CUSTOM
    op.execute(
        """
        UPDATE item_barcodes
           SET symbology = CASE
             WHEN upper(btrim(kind)) IN ('EAN8', 'UPC', 'UPC12', 'EAN13', 'GS1', 'CUSTOM', 'ITF14')
               THEN upper(btrim(kind))
             ELSE 'CUSTOM'
           END
        """
    )

    # 5) item_uom_id 回填到各 item 的 base uom
    op.execute(
        """
        UPDATE item_barcodes AS b
           SET item_uom_id = u.id
          FROM item_uoms AS u
         WHERE u.item_id = b.item_id
           AND u.is_base = true
           AND b.item_uom_id IS NULL
        """
    )

    # 6) 严格校验：不允许存在无法绑定 base uom 的历史条码
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
              FROM item_barcodes
             WHERE item_uom_id IS NULL
          ) THEN
            RAISE EXCEPTION 'item_barcodes.item_uom_id backfill failed: some rows have no base item_uom';
          END IF;
        END
        $$;
        """
    )

    # 7) 复合外键：强制 item_uom_id 必须属于同一个 item
    op.create_foreign_key(
        "fk_item_barcodes_item_uom_pair",
        "item_barcodes",
        "item_uoms",
        ["item_uom_id", "item_id"],
        ["id", "item_id"],
    )

    # 8) 收紧为终态
    op.alter_column(
        "item_barcodes",
        "item_uom_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "item_barcodes",
        "symbology",
        existing_type=sa.Text(),
        nullable=False,
        server_default=None,
    )

    # 9) 退役旧脏字段 kind
    op.drop_column("item_barcodes", "kind")


def downgrade() -> None:
    """Downgrade schema."""

    # 1) 恢复旧字段 kind
    op.add_column(
        "item_barcodes",
        sa.Column(
            "kind",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'CUSTOM'"),
            comment="条码类型：EAN13 / UPC / INNER / CUSTOM ...",
        ),
    )

    # 2) kind 近似恢复：从 symbology 回写
    op.execute(
        """
        UPDATE item_barcodes
           SET kind = CASE
             WHEN upper(btrim(symbology)) IN ('EAN8', 'UPC', 'UPC12', 'EAN13', 'GS1', 'CUSTOM', 'ITF14')
               THEN upper(btrim(symbology))
             ELSE 'CUSTOM'
           END
        """
    )

    # 3) 先拆掉 uom 级绑定
    op.drop_constraint(
        "fk_item_barcodes_item_uom_pair",
        "item_barcodes",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_item_barcodes_item_uom_id",
        table_name="item_barcodes",
    )
    op.drop_column("item_barcodes", "item_uom_id")
    op.drop_column("item_barcodes", "symbology")

    # 4) item_id 类型恢复成 bigint
    op.drop_constraint(
        "item_barcodes_item_id_fkey",
        "item_barcodes",
        type_="foreignkey",
    )
    op.alter_column(
        "item_barcodes",
        "item_id",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
        postgresql_using="item_id::bigint",
    )
    op.create_foreign_key(
        "item_barcodes_item_id_fkey",
        "item_barcodes",
        "items",
        ["item_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 5) 回滚 item_uoms 的复合唯一键
    op.drop_constraint(
        "uq_item_uoms_id_item_id",
        "item_uoms",
        type_="unique",
    )
