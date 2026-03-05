"""phase5 inbound receipts guardrails

Revision ID: c256687896bc
Revises: f444321b4e0b
Create Date: 2026-02-18 20:17:43.126891

- inbound_receipts.status default -> 'DRAFT'
- inbound_receipts.ref UNIQUE
- PO DRAFT partial unique index
- inbound_receipt_lines add barcode snapshot column
- drop duplicate item_id index on inbound_receipt_lines
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c256687896bc"
down_revision: Union[str, Sequence[str], None] = "f444321b4e0b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ensure_no_duplicate_ref() -> None:
    """Fail fast if inbound_receipts.ref has duplicates."""
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            """
            SELECT ref, COUNT(*) AS c
            FROM inbound_receipts
            GROUP BY ref
            HAVING COUNT(*) > 1
            ORDER BY c DESC
            LIMIT 1
            """
        )
    ).fetchone()

    if row is not None:
        raise RuntimeError(
            f"[phase5 guardrails] duplicate ref detected: ref={row[0]!r}, count={row[1]}"
        )


def _ensure_no_duplicate_po_draft() -> None:
    """Fail fast if multiple PO DRAFT receipts already exist."""
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            """
            SELECT source_type, source_id, COUNT(*) AS c
            FROM inbound_receipts
            WHERE source_type = 'PO'
              AND source_id IS NOT NULL
              AND status = 'DRAFT'
            GROUP BY source_type, source_id
            HAVING COUNT(*) > 1
            ORDER BY c DESC
            LIMIT 1
            """
        )
    ).fetchone()

    if row is not None:
        raise RuntimeError(
            "[phase5 guardrails] duplicate PO draft detected: "
            f"source_type={row[0]!r}, source_id={row[1]!r}, count={row[2]}"
        )


def upgrade() -> None:
    # 1️⃣ status 默认改为 DRAFT
    op.alter_column(
        "inbound_receipts",
        "status",
        existing_type=sa.VARCHAR(length=32),
        server_default=sa.text("'DRAFT'"),
        existing_nullable=False,
    )

    # 2️⃣ ref 唯一化
    _ensure_no_duplicate_ref()

    # 删除旧的非唯一索引
    op.drop_index("ix_inbound_receipts_ref", table_name="inbound_receipts")

    # 新建唯一索引
    op.create_index(
        "uq_inbound_receipts_ref",
        "inbound_receipts",
        ["ref"],
        unique=True,
    )

    # 3️⃣ PO DRAFT partial unique
    _ensure_no_duplicate_po_draft()

    op.create_index(
        "uq_inbound_receipts_po_draft",
        "inbound_receipts",
        ["source_type", "source_id"],
        unique=True,
        postgresql_where=sa.text(
            "source_type = 'PO' AND source_id IS NOT NULL AND status = 'DRAFT'"
        ),
    )

    # 4️⃣ receipt_lines 增加 barcode 快照字段
    op.add_column(
        "inbound_receipt_lines",
        sa.Column("barcode", sa.VARCHAR(length=128), nullable=True),
    )

    # 5️⃣ 删除重复 item_id 索引
    # 当前存在：
    # ix_inbound_receipt_lines_item
    # ix_inbound_receipt_lines_item_id
    # 保留 ix_inbound_receipt_lines_item，删除 item_id 那个重复索引
    op.drop_index(
        "ix_inbound_receipt_lines_item_id",
        table_name="inbound_receipt_lines",
    )


def downgrade() -> None:
    # 恢复重复索引
    op.create_index(
        "ix_inbound_receipt_lines_item_id",
        "inbound_receipt_lines",
        ["item_id"],
        unique=False,
    )

    # 删除 barcode
    op.drop_column("inbound_receipt_lines", "barcode")

    # 删除 partial unique
    op.drop_index(
        "uq_inbound_receipts_po_draft",
        table_name="inbound_receipts",
    )

    # 删除唯一 ref 索引并恢复旧索引
    op.drop_index(
        "uq_inbound_receipts_ref",
        table_name="inbound_receipts",
    )

    op.create_index(
        "ix_inbound_receipts_ref",
        "inbound_receipts",
        ["ref"],
        unique=False,
    )

    # 恢复 status 默认值为 CONFIRMED（旧行为）
    op.alter_column(
        "inbound_receipts",
        "status",
        existing_type=sa.VARCHAR(length=32),
        server_default=sa.text("'CONFIRMED'"),
        existing_nullable=False,
    )
