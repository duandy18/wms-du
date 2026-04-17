"""refactor inbound receipts task model and add wms inbound operations

Revision ID: bb5d85b12ff8
Revises: 4fb9df42573f
Create Date: 2026-04-17 16:45:30.459228

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "bb5d85b12ff8"
down_revision: Union[str, Sequence[str], None] = "4fb9df42573f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # inbound_receipts: 旧“收货事实混合表” -> 新“入库任务头表”
    # ------------------------------------------------------------------
    op.execute("DROP INDEX IF EXISTS uq_inbound_receipts_po_draft")
    op.execute("DROP INDEX IF EXISTS uq_inbound_receipts_ref")
    op.execute("DROP INDEX IF EXISTS ix_inbound_receipts_trace")
    op.execute("DROP INDEX IF EXISTS ix_inbound_receipts_occurred_at")

    op.alter_column(
        "inbound_receipts",
        "supplier_name",
        new_column_name="counterparty_name_snapshot",
        existing_type=sa.String(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "inbound_receipts",
        "source_id",
        new_column_name="source_doc_id",
        existing_type=sa.Integer(),
        existing_nullable=True,
    )
    op.alter_column(
        "inbound_receipts",
        "ref",
        new_column_name="receipt_no",
        existing_type=sa.String(length=128),
        existing_nullable=False,
    )

    op.add_column(
        "inbound_receipts",
        sa.Column("source_doc_no_snapshot", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "inbound_receipts",
        sa.Column("warehouse_name_snapshot", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "inbound_receipts",
        sa.Column("created_by", sa.Integer(), nullable=True),
    )
    op.add_column(
        "inbound_receipts",
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 先按旧列值完成状态/来源映射与 released_at 回填
    op.execute(
        """
        UPDATE inbound_receipts
        SET
          source_type = CASE
            WHEN upper(source_type) IN ('PO', 'PURCHASE', 'PURCHASE_ORDER') THEN 'PURCHASE_ORDER'
            WHEN upper(source_type) IN ('RETURN', 'RETURN_ORDER', 'RMA') THEN 'RETURN_ORDER'
            ELSE 'MANUAL'
          END,
          status = CASE
            WHEN upper(status) = 'DRAFT' THEN 'DRAFT'
            WHEN upper(status) = 'VOIDED' THEN 'VOIDED'
            ELSE 'RELEASED'
          END,
          released_at = CASE
            WHEN upper(status) = 'DRAFT' THEN NULL
            ELSE COALESCE(occurred_at, updated_at, created_at, now())
          END
        """
    )

    # 仓库名快照：只在 warehouses 表存在 name/code 时回填，不猜字段
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'warehouses'
              AND column_name = 'name'
          ) THEN
            EXECUTE '
              UPDATE inbound_receipts r
              SET warehouse_name_snapshot = w.name
              FROM warehouses w
              WHERE w.id = r.warehouse_id
            ';
          ELSIF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'warehouses'
              AND column_name = 'code'
          ) THEN
            EXECUTE '
              UPDATE inbound_receipts r
              SET warehouse_name_snapshot = w.code
              FROM warehouses w
              WHERE w.id = r.warehouse_id
            ';
          END IF;
        END $$;
        """
    )

    op.alter_column(
        "inbound_receipts",
        "source_type",
        existing_type=sa.String(length=16),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
    op.alter_column(
        "inbound_receipts",
        "status",
        existing_type=sa.String(length=32),
        type_=sa.String(length=16),
        existing_nullable=False,
    )
    op.alter_column(
        "inbound_receipts",
        "remark",
        existing_type=sa.String(length=255),
        type_=sa.String(length=500),
        existing_nullable=True,
    )

    op.create_foreign_key(
        "fk_inbound_receipts_created_by",
        "inbound_receipts",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_inbound_receipts_receipt_no",
        "inbound_receipts",
        ["receipt_no"],
    )
    op.create_check_constraint(
        "ck_inbound_receipts_source_type",
        "inbound_receipts",
        "source_type IN ('PURCHASE_ORDER', 'MANUAL', 'RETURN_ORDER')",
    )
    op.create_check_constraint(
        "ck_inbound_receipts_status",
        "inbound_receipts",
        "status IN ('DRAFT', 'RELEASED', 'VOIDED')",
    )

    op.drop_column("inbound_receipts", "trace_id")
    op.drop_column("inbound_receipts", "occurred_at")

    # ------------------------------------------------------------------
    # inbound_receipt_lines: 旧“收货事实行” -> 新“入库任务行”
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TABLE inbound_receipt_lines DROP CONSTRAINT IF EXISTS ck_receipt_lines_lot_required_on_confirmed"
    )
    op.execute(
        "ALTER TABLE inbound_receipt_lines DROP CONSTRAINT IF EXISTS ck_receipt_lines_status_snapshot_enum"
    )
    op.execute(
        "ALTER TABLE inbound_receipt_lines DROP CONSTRAINT IF EXISTS fk_inbound_receipt_lines_lot_dims"
    )
    op.execute(
        "ALTER TABLE inbound_receipt_lines DROP CONSTRAINT IF EXISTS fk_inbound_receipt_lines_warehouse"
    )
    op.execute(
        "ALTER TABLE inbound_receipt_lines DROP CONSTRAINT IF EXISTS fk_inbound_receipt_lines_po_line"
    )
    op.execute(
        "ALTER TABLE inbound_receipt_lines DROP CONSTRAINT IF EXISTS ck_receipt_qty_base_consistent"
    )
    op.execute("DROP INDEX IF EXISTS ix_inbound_receipt_lines_po_line_id")

    op.alter_column(
        "inbound_receipt_lines",
        "receipt_id",
        new_column_name="inbound_receipt_id",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )
    op.alter_column(
        "inbound_receipt_lines",
        "po_line_id",
        new_column_name="source_line_id",
        existing_type=sa.Integer(),
        existing_nullable=True,
    )
    op.alter_column(
        "inbound_receipt_lines",
        "uom_id",
        new_column_name="item_uom_id",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )
    op.alter_column(
        "inbound_receipt_lines",
        "qty_input",
        new_column_name="planned_qty",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.execute(
        """
        ALTER TABLE inbound_receipt_lines
        RENAME CONSTRAINT fk_receipt_line_uom TO fk_inbound_receipt_lines_item_uom
        """
    )

    op.add_column(
        "inbound_receipt_lines",
        sa.Column("item_name_snapshot", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "inbound_receipt_lines",
        sa.Column("item_spec_snapshot", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "inbound_receipt_lines",
        sa.Column("uom_name_snapshot", sa.String(length=64), nullable=True),
    )

    op.alter_column(
        "inbound_receipt_lines",
        "planned_qty",
        existing_type=sa.Integer(),
        type_=sa.Numeric(18, 6),
        existing_nullable=False,
        postgresql_using="planned_qty::numeric(18,6)",
    )
    op.alter_column(
        "inbound_receipt_lines",
        "ratio_to_base_snapshot",
        existing_type=sa.Integer(),
        type_=sa.Numeric(18, 6),
        existing_nullable=False,
        postgresql_using="ratio_to_base_snapshot::numeric(18,6)",
    )
    op.alter_column(
        "inbound_receipt_lines",
        "remark",
        existing_type=sa.String(length=255),
        type_=sa.String(length=500),
        existing_nullable=True,
    )

    # 商品名/规格/单位快照：只在真实列存在时回填，不猜字段
    op.execute(
        """
        DO $$
        DECLARE
          v_item_name_col text;
          v_item_spec_col text;
          v_uom_name_col text;
        BEGIN
          SELECT CASE
                   WHEN EXISTS (
                     SELECT 1 FROM information_schema.columns
                     WHERE table_schema = 'public' AND table_name = 'items' AND column_name = 'name'
                   ) THEN 'name'
                   WHEN EXISTS (
                     SELECT 1 FROM information_schema.columns
                     WHERE table_schema = 'public' AND table_name = 'items' AND column_name = 'item_name'
                   ) THEN 'item_name'
                   ELSE NULL
                 END
          INTO v_item_name_col;

          IF v_item_name_col IS NOT NULL THEN
            EXECUTE format(
              'UPDATE inbound_receipt_lines l
               SET item_name_snapshot = i.%I
               FROM items i
               WHERE i.id = l.item_id',
              v_item_name_col
            );
          END IF;

          SELECT CASE
                   WHEN EXISTS (
                     SELECT 1 FROM information_schema.columns
                     WHERE table_schema = 'public' AND table_name = 'items' AND column_name = 'spec_text'
                   ) THEN 'spec_text'
                   WHEN EXISTS (
                     SELECT 1 FROM information_schema.columns
                     WHERE table_schema = 'public' AND table_name = 'items' AND column_name = 'spec'
                   ) THEN 'spec'
                   WHEN EXISTS (
                     SELECT 1 FROM information_schema.columns
                     WHERE table_schema = 'public' AND table_name = 'items' AND column_name = 'specification'
                   ) THEN 'specification'
                   ELSE NULL
                 END
          INTO v_item_spec_col;

          IF v_item_spec_col IS NOT NULL THEN
            EXECUTE format(
              'UPDATE inbound_receipt_lines l
               SET item_spec_snapshot = i.%I
               FROM items i
               WHERE i.id = l.item_id',
              v_item_spec_col
            );
          END IF;

          SELECT CASE
                   WHEN EXISTS (
                     SELECT 1 FROM information_schema.columns
                     WHERE table_schema = 'public' AND table_name = 'item_uoms' AND column_name = 'display_name'
                   ) THEN 'display_name'
                   WHEN EXISTS (
                     SELECT 1 FROM information_schema.columns
                     WHERE table_schema = 'public' AND table_name = 'item_uoms' AND column_name = 'uom_name'
                   ) THEN 'uom_name'
                   WHEN EXISTS (
                     SELECT 1 FROM information_schema.columns
                     WHERE table_schema = 'public' AND table_name = 'item_uoms' AND column_name = 'uom'
                   ) THEN 'uom'
                   ELSE NULL
                 END
          INTO v_uom_name_col;

          IF v_uom_name_col IS NOT NULL THEN
            EXECUTE format(
              'UPDATE inbound_receipt_lines l
               SET uom_name_snapshot = u.%I
               FROM item_uoms u
               WHERE u.id = l.item_uom_id',
              v_uom_name_col
            );
          END IF;
        END $$;
        """
    )

    op.drop_column("inbound_receipt_lines", "production_date")
    op.drop_column("inbound_receipt_lines", "expiry_date")
    op.drop_column("inbound_receipt_lines", "unit_cost")
    op.drop_column("inbound_receipt_lines", "line_amount")
    op.drop_column("inbound_receipt_lines", "lot_id")
    op.drop_column("inbound_receipt_lines", "warehouse_id")
    op.drop_column("inbound_receipt_lines", "qty_base")
    op.drop_column("inbound_receipt_lines", "receipt_status_snapshot")
    op.drop_column("inbound_receipt_lines", "lot_code_input")

    op.create_check_constraint(
        "ck_inbound_receipt_lines_planned_qty_positive",
        "inbound_receipt_lines",
        "planned_qty > 0",
    )
    op.create_check_constraint(
        "ck_inbound_receipt_lines_ratio_positive",
        "inbound_receipt_lines",
        "ratio_to_base_snapshot > 0",
    )

    # ------------------------------------------------------------------
    # 新建 WMS 收货操作事实表
    # ------------------------------------------------------------------
    op.create_table(
        "wms_inbound_operations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("receipt_no_snapshot", sa.String(length=64), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("warehouse_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("supplier_id", sa.Integer(), nullable=True),
        sa.Column("supplier_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("operator_id", sa.Integer(), nullable=True),
        sa.Column("operator_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("operated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("remark", sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_wms_inbound_operations")),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            name="fk_wms_inbound_operations_warehouse",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
            name="fk_wms_inbound_operations_supplier",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["operator_id"],
            ["users.id"],
            name="fk_wms_inbound_operations_operator",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_wms_inbound_operations_receipt_no",
        "wms_inbound_operations",
        ["receipt_no_snapshot"],
        unique=False,
    )
    op.create_index(
        "ix_wms_inbound_operations_operated_at",
        "wms_inbound_operations",
        ["operated_at"],
        unique=False,
    )
    op.create_index(
        "ix_wms_inbound_operations_warehouse_operated_at",
        "wms_inbound_operations",
        ["warehouse_id", "operated_at"],
        unique=False,
    )

    op.create_table(
        "wms_inbound_operation_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("wms_inbound_operation_id", sa.Integer(), nullable=False),
        sa.Column("receipt_line_no_snapshot", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("item_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("item_spec_snapshot", sa.String(length=255), nullable=True),
        sa.Column("item_uom_id", sa.Integer(), nullable=False),
        sa.Column("uom_name_snapshot", sa.String(length=64), nullable=True),
        sa.Column("ratio_to_base_snapshot", sa.Numeric(18, 6), nullable=False),
        sa.Column("qty_inbound", sa.Numeric(18, 6), nullable=False),
        sa.Column("qty_base", sa.Numeric(18, 6), nullable=False),
        sa.Column("batch_no", sa.String(length=128), nullable=True),
        sa.Column("production_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("lot_id", sa.Integer(), nullable=True),
        sa.Column("remark", sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_wms_inbound_operation_lines")),
        sa.CheckConstraint(
            "(production_date IS NULL) OR (expiry_date IS NULL) OR (production_date <= expiry_date)",
            name="ck_wms_inbound_operation_lines_prod_le_exp",
        ),
        sa.CheckConstraint(
            "ratio_to_base_snapshot > 0",
            name="ck_wms_inbound_operation_lines_ratio_positive",
        ),
        sa.CheckConstraint(
            "qty_inbound > 0",
            name="ck_wms_inbound_operation_lines_qty_inbound_positive",
        ),
        sa.CheckConstraint(
            "qty_base > 0",
            name="ck_wms_inbound_operation_lines_qty_base_positive",
        ),
        sa.CheckConstraint(
            "qty_base = (qty_inbound * ratio_to_base_snapshot)",
            name="ck_wms_inbound_operation_lines_qty_base_consistent",
        ),
        sa.ForeignKeyConstraint(
            ["wms_inbound_operation_id"],
            ["wms_inbound_operations.id"],
            name="fk_wms_inbound_operation_lines_operation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            name="fk_wms_inbound_operation_lines_item",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["item_uom_id"],
            ["item_uoms.id"],
            name="fk_wms_inbound_operation_lines_item_uom",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["lot_id"],
            ["lots.id"],
            name="fk_wms_inbound_operation_lines_lot",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_wms_inbound_operation_lines_operation_id",
        "wms_inbound_operation_lines",
        ["wms_inbound_operation_id"],
        unique=False,
    )
    op.create_index(
        "ix_wms_inbound_operation_lines_receipt_line_no",
        "wms_inbound_operation_lines",
        ["receipt_line_no_snapshot"],
        unique=False,
    )
    op.create_index(
        "ix_wms_inbound_operation_lines_lot_id",
        "wms_inbound_operation_lines",
        ["lot_id"],
        unique=False,
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # best-effort downgrade:
    # 1) 删除新建的 wms_inbound_operations 两张表
    # 2) 将 inbound_receipts / inbound_receipt_lines 尽量恢复到旧结构
    # ------------------------------------------------------------------
    op.drop_index("ix_wms_inbound_operation_lines_lot_id", table_name="wms_inbound_operation_lines")
    op.drop_index("ix_wms_inbound_operation_lines_receipt_line_no", table_name="wms_inbound_operation_lines")
    op.drop_index("ix_wms_inbound_operation_lines_operation_id", table_name="wms_inbound_operation_lines")
    op.drop_table("wms_inbound_operation_lines")

    op.drop_index("ix_wms_inbound_operations_warehouse_operated_at", table_name="wms_inbound_operations")
    op.drop_index("ix_wms_inbound_operations_operated_at", table_name="wms_inbound_operations")
    op.drop_index("ix_wms_inbound_operations_receipt_no", table_name="wms_inbound_operations")
    op.drop_table("wms_inbound_operations")

    # ------------------------------------------------------------------
    # inbound_receipt_lines: best-effort restore old shape
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TABLE inbound_receipt_lines DROP CONSTRAINT IF EXISTS ck_inbound_receipt_lines_planned_qty_positive"
    )
    op.execute(
        "ALTER TABLE inbound_receipt_lines DROP CONSTRAINT IF EXISTS ck_inbound_receipt_lines_ratio_positive"
    )

    op.alter_column(
        "inbound_receipt_lines",
        "inbound_receipt_id",
        new_column_name="receipt_id",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )
    op.alter_column(
        "inbound_receipt_lines",
        "source_line_id",
        new_column_name="po_line_id",
        existing_type=sa.Integer(),
        existing_nullable=True,
    )
    op.alter_column(
        "inbound_receipt_lines",
        "item_uom_id",
        new_column_name="uom_id",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )
    op.alter_column(
        "inbound_receipt_lines",
        "planned_qty",
        new_column_name="qty_input",
        existing_type=sa.Numeric(18, 6),
        existing_nullable=False,
    )

    op.execute(
        """
        ALTER TABLE inbound_receipt_lines
        RENAME CONSTRAINT fk_inbound_receipt_lines_item_uom TO fk_receipt_line_uom
        """
    )

    op.alter_column(
        "inbound_receipt_lines",
        "qty_input",
        existing_type=sa.Numeric(18, 6),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using="GREATEST(1, round(qty_input)::int)",
    )
    op.alter_column(
        "inbound_receipt_lines",
        "ratio_to_base_snapshot",
        existing_type=sa.Numeric(18, 6),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using="GREATEST(1, round(ratio_to_base_snapshot)::int)",
    )
    op.alter_column(
        "inbound_receipt_lines",
        "remark",
        existing_type=sa.String(length=500),
        type_=sa.String(length=255),
        existing_nullable=True,
    )

    op.add_column(
        "inbound_receipt_lines",
        sa.Column("production_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "inbound_receipt_lines",
        sa.Column("expiry_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "inbound_receipt_lines",
        sa.Column("unit_cost", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "inbound_receipt_lines",
        sa.Column("line_amount", sa.Numeric(14, 2), nullable=True),
    )
    op.add_column(
        "inbound_receipt_lines",
        sa.Column("lot_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "inbound_receipt_lines",
        sa.Column("warehouse_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "inbound_receipt_lines",
        sa.Column("qty_base", sa.Integer(), nullable=True),
    )
    op.add_column(
        "inbound_receipt_lines",
        sa.Column(
            "receipt_status_snapshot",
            sa.String(length=32),
            nullable=False,
            server_default="DRAFT",
        ),
    )
    op.add_column(
        "inbound_receipt_lines",
        sa.Column("lot_code_input", sa.String(length=64), nullable=True),
    )

    op.execute(
        """
        UPDATE inbound_receipt_lines l
        SET
          warehouse_id = r.warehouse_id,
          qty_base = (l.qty_input * l.ratio_to_base_snapshot),
          receipt_status_snapshot = 'DRAFT'
        FROM inbound_receipts r
        WHERE r.id = l.receipt_id
        """
    )
    op.execute(
        """
        UPDATE inbound_receipt_lines l
        SET po_line_id = NULL
        FROM inbound_receipts r
        WHERE r.id = l.receipt_id
          AND r.source_type <> 'PURCHASE_ORDER'
        """
    )

    op.alter_column(
        "inbound_receipt_lines",
        "warehouse_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "inbound_receipt_lines",
        "qty_base",
        existing_type=sa.Integer(),
        nullable=False,
    )

    op.drop_column("inbound_receipt_lines", "item_name_snapshot")
    op.drop_column("inbound_receipt_lines", "item_spec_snapshot")
    op.drop_column("inbound_receipt_lines", "uom_name_snapshot")

    op.create_index(
        "ix_inbound_receipt_lines_po_line_id",
        "inbound_receipt_lines",
        ["po_line_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_inbound_receipt_lines_po_line",
        "inbound_receipt_lines",
        "purchase_order_lines",
        ["po_line_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_inbound_receipt_lines_warehouse",
        "inbound_receipt_lines",
        "warehouses",
        ["warehouse_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_inbound_receipt_lines_lot_dims",
        "inbound_receipt_lines",
        "lots",
        ["lot_id", "warehouse_id", "item_id"],
        ["id", "warehouse_id", "item_id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_inbound_receipt_lines_prod_le_exp",
        "inbound_receipt_lines",
        "(production_date IS NULL) OR (expiry_date IS NULL) OR (production_date <= expiry_date)",
    )
    op.create_check_constraint(
        "ck_receipt_qty_base_consistent",
        "inbound_receipt_lines",
        "qty_base = (qty_input * ratio_to_base_snapshot)",
    )
    op.create_check_constraint(
        "ck_receipt_lines_status_snapshot_enum",
        "inbound_receipt_lines",
        "receipt_status_snapshot IN ('DRAFT', 'CONFIRMED')",
    )
    op.create_check_constraint(
        "ck_receipt_lines_lot_required_on_confirmed",
        "inbound_receipt_lines",
        "receipt_status_snapshot <> 'CONFIRMED' OR lot_id IS NOT NULL",
    )

    # ------------------------------------------------------------------
    # inbound_receipts: best-effort restore old shape
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TABLE inbound_receipts DROP CONSTRAINT IF EXISTS ck_inbound_receipts_source_type"
    )
    op.execute(
        "ALTER TABLE inbound_receipts DROP CONSTRAINT IF EXISTS ck_inbound_receipts_status"
    )
    op.drop_constraint(
        "fk_inbound_receipts_created_by",
        "inbound_receipts",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_inbound_receipts_receipt_no",
        "inbound_receipts",
        type_="unique",
    )

    op.add_column(
        "inbound_receipts",
        sa.Column("trace_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "inbound_receipts",
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.execute(
        """
        UPDATE inbound_receipts
        SET
          source_type = CASE
            WHEN source_type = 'PURCHASE_ORDER' THEN 'PO'
            WHEN source_type = 'RETURN_ORDER' THEN 'RETURN'
            ELSE 'MANUAL'
          END,
          status = CASE
            WHEN status = 'DRAFT' THEN 'DRAFT'
            ELSE 'CONFIRMED'
          END,
          occurred_at = COALESCE(released_at, created_at, updated_at, now())
        """
    )

    op.alter_column(
        "inbound_receipts",
        "source_type",
        existing_type=sa.String(length=32),
        type_=sa.String(length=16),
        existing_nullable=False,
    )
    op.alter_column(
        "inbound_receipts",
        "status",
        existing_type=sa.String(length=16),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
    op.alter_column(
        "inbound_receipts",
        "remark",
        existing_type=sa.String(length=500),
        type_=sa.String(length=255),
        existing_nullable=True,
    )

    op.alter_column(
        "inbound_receipts",
        "counterparty_name_snapshot",
        new_column_name="supplier_name",
        existing_type=sa.String(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "inbound_receipts",
        "source_doc_id",
        new_column_name="source_id",
        existing_type=sa.Integer(),
        existing_nullable=True,
    )
    op.alter_column(
        "inbound_receipts",
        "receipt_no",
        new_column_name="ref",
        existing_type=sa.String(length=128),
        existing_nullable=False,
    )

    op.alter_column(
        "inbound_receipts",
        "occurred_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )

    op.drop_column("inbound_receipts", "source_doc_no_snapshot")
    op.drop_column("inbound_receipts", "warehouse_name_snapshot")
    op.drop_column("inbound_receipts", "created_by")
    op.drop_column("inbound_receipts", "released_at")

    op.create_index(
        "uq_inbound_receipts_ref",
        "inbound_receipts",
        ["ref"],
        unique=True,
    )
    op.create_index(
        "uq_inbound_receipts_po_draft",
        "inbound_receipts",
        ["source_type", "source_id"],
        unique=True,
        postgresql_where=sa.text(
            "source_type = 'PO' AND source_id IS NOT NULL AND status = 'DRAFT'"
        ),
    )
    op.create_index(
        "ix_inbound_receipts_trace",
        "inbound_receipts",
        ["trace_id"],
        unique=False,
    )
    op.create_index(
        "ix_inbound_receipts_occurred_at",
        "inbound_receipts",
        ["occurred_at"],
        unique=False,
    )
