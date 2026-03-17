"""billing add import_batch_id foreign keys

Revision ID: 519ebdffcf18
Revises: 4e086e9148ec
Create Date: 2026-03-17 19:12:13.109751

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "519ebdffcf18"
down_revision: Union[str, Sequence[str], None] = "4e086e9148ec"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1) 新建：账单导入批次头表
    # -------------------------------------------------------------------------
    op.create_table(
        "carrier_bill_import_batches",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("carrier_code", sa.String(length=32), nullable=False),
        sa.Column("import_batch_no", sa.String(length=64), nullable=False),
        sa.Column("bill_month", sa.String(length=16), nullable=True),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'imported'"),
        ),
        sa.Column(
            "row_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "success_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "error_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('imported', 'reconciled', 'failed', 'archived')",
            name="ck_carrier_bill_import_batches_status",
        ),
    )

    op.create_index(
        "uq_carrier_bill_import_batches_carrier_batch",
        "carrier_bill_import_batches",
        ["carrier_code", "import_batch_no"],
        unique=True,
    )
    op.create_index(
        "ix_carrier_bill_import_batches_bill_month",
        "carrier_bill_import_batches",
        ["bill_month"],
        unique=False,
    )
    op.create_index(
        "ix_carrier_bill_import_batches_imported_at",
        "carrier_bill_import_batches",
        ["imported_at"],
        unique=False,
    )

    # -------------------------------------------------------------------------
    # 2) 给明细表 / 对账表加 import_batch_id（先 nullable，便于回填）
    # -------------------------------------------------------------------------
    op.add_column(
        "carrier_bill_items",
        sa.Column("import_batch_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "shipping_record_reconciliations",
        sa.Column("import_batch_id", sa.BigInteger(), nullable=True),
    )

    # -------------------------------------------------------------------------
    # 3) 基于现有 carrier_bill_items 回填批次头表
    #
    # 说明：
    # - 这里以 (carrier_code, import_batch_no) 为现存业务边界；
    # - bill_month 用同批次内 MAX(bill_month) 归并；
    # - source_filename 暂无历史来源，留空；
    # - row_count / success_count 按已存在明细行数回填；
    # -------------------------------------------------------------------------
    op.execute(
        """
        INSERT INTO carrier_bill_import_batches (
            carrier_code,
            import_batch_no,
            bill_month,
            source_filename,
            status,
            row_count,
            success_count,
            error_count
        )
        SELECT
            cbi.carrier_code,
            cbi.import_batch_no,
            MAX(cbi.bill_month) AS bill_month,
            NULL AS source_filename,
            'imported' AS status,
            COUNT(*)::int AS row_count,
            COUNT(*)::int AS success_count,
            0 AS error_count
        FROM carrier_bill_items cbi
        GROUP BY cbi.carrier_code, cbi.import_batch_no
        """
    )

    # -------------------------------------------------------------------------
    # 4) 回填 carrier_bill_items.import_batch_id
    # -------------------------------------------------------------------------
    op.execute(
        """
        UPDATE carrier_bill_items cbi
        SET import_batch_id = cbib.id
        FROM carrier_bill_import_batches cbib
        WHERE cbib.carrier_code = cbi.carrier_code
          AND cbib.import_batch_no = cbi.import_batch_no
        """
    )

    # -------------------------------------------------------------------------
    # 5) 回填 shipping_record_reconciliations.import_batch_id
    # -------------------------------------------------------------------------
    op.execute(
        """
        UPDATE shipping_record_reconciliations r
        SET import_batch_id = cbib.id
        FROM carrier_bill_import_batches cbib
        WHERE cbib.carrier_code = r.carrier_code
          AND cbib.import_batch_no = r.import_batch_no
        """
    )

    # -------------------------------------------------------------------------
    # 6) 非空约束
    # -------------------------------------------------------------------------
    op.alter_column(
        "carrier_bill_items",
        "import_batch_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.alter_column(
        "shipping_record_reconciliations",
        "import_batch_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )

    # -------------------------------------------------------------------------
    # 7) 外键约束
    # -------------------------------------------------------------------------
    op.create_foreign_key(
        "fk_carrier_bill_items_import_batch_id",
        "carrier_bill_items",
        "carrier_bill_import_batches",
        ["import_batch_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_shipping_record_reconciliations_import_batch_id",
        "shipping_record_reconciliations",
        "carrier_bill_import_batches",
        ["import_batch_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # -------------------------------------------------------------------------
    # 8) 新索引
    # -------------------------------------------------------------------------
    op.create_index(
        "ix_carrier_bill_items_import_batch_id",
        "carrier_bill_items",
        ["import_batch_id"],
        unique=False,
    )

    op.create_index(
        "ix_shipping_record_reconciliations_import_batch_id",
        "shipping_record_reconciliations",
        ["import_batch_id"],
        unique=False,
    )

    # 旧索引：字符串组合
    op.drop_index(
        "ix_shipping_record_reconciliations_carrier_batch_status",
        table_name="shipping_record_reconciliations",
    )

    # 新索引：批次ID + 状态
    op.create_index(
        "ix_shipping_record_reconciliations_batch_status",
        "shipping_record_reconciliations",
        ["import_batch_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    # -------------------------------------------------------------------------
    # 1) 恢复 reconciliation 旧索引
    # -------------------------------------------------------------------------
    op.drop_index(
        "ix_shipping_record_reconciliations_batch_status",
        table_name="shipping_record_reconciliations",
    )
    op.create_index(
        "ix_shipping_record_reconciliations_carrier_batch_status",
        "shipping_record_reconciliations",
        ["carrier_code", "import_batch_no", "status"],
        unique=False,
    )

    # -------------------------------------------------------------------------
    # 2) 删除新索引
    # -------------------------------------------------------------------------
    op.drop_index(
        "ix_shipping_record_reconciliations_import_batch_id",
        table_name="shipping_record_reconciliations",
    )
    op.drop_index(
        "ix_carrier_bill_items_import_batch_id",
        table_name="carrier_bill_items",
    )

    # -------------------------------------------------------------------------
    # 3) 删除外键
    # -------------------------------------------------------------------------
    op.drop_constraint(
        "fk_shipping_record_reconciliations_import_batch_id",
        "shipping_record_reconciliations",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_carrier_bill_items_import_batch_id",
        "carrier_bill_items",
        type_="foreignkey",
    )

    # -------------------------------------------------------------------------
    # 4) 删除列
    # -------------------------------------------------------------------------
    op.drop_column("shipping_record_reconciliations", "import_batch_id")
    op.drop_column("carrier_bill_items", "import_batch_id")

    # -------------------------------------------------------------------------
    # 5) 删除批次头表索引
    # -------------------------------------------------------------------------
    op.drop_index(
        "ix_carrier_bill_import_batches_imported_at",
        table_name="carrier_bill_import_batches",
    )
    op.drop_index(
        "ix_carrier_bill_import_batches_bill_month",
        table_name="carrier_bill_import_batches",
    )
    op.drop_index(
        "uq_carrier_bill_import_batches_carrier_batch",
        table_name="carrier_bill_import_batches",
    )

    # -------------------------------------------------------------------------
    # 6) 删除批次头表
    # -------------------------------------------------------------------------
    op.drop_table("carrier_bill_import_batches")
