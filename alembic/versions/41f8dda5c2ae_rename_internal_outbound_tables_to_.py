"""rename internal outbound tables to manual outbound

Revision ID: 41f8dda5c2ae
Revises: 17f99d5d97cf
Create Date: 2026-04-19 20:50:02.683991

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "41f8dda5c2ae"
down_revision: Union[str, Sequence[str], None] = "17f99d5d97cf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("internal_outbound_docs", "manual_outbound_docs")
    op.rename_table("internal_outbound_lines", "manual_outbound_lines")

    op.execute(
        """
        ALTER INDEX IF EXISTS ix_internal_outbound_docs_status
        RENAME TO ix_manual_outbound_docs_status
        """
    )
    op.execute(
        """
        ALTER INDEX IF EXISTS ix_internal_outbound_docs_trace_id
        RENAME TO ix_manual_outbound_docs_trace_id
        """
    )
    op.execute(
        """
        ALTER INDEX IF EXISTS ix_internal_outbound_docs_warehouse_doc_no
        RENAME TO ix_manual_outbound_docs_warehouse_doc_no
        """
    )
    op.execute(
        """
        ALTER INDEX IF EXISTS ix_internal_outbound_lines_doc_id
        RENAME TO ix_manual_outbound_lines_doc_id
        """
    )
    op.execute(
        """
        ALTER INDEX IF EXISTS ix_internal_outbound_lines_item_id
        RENAME TO ix_manual_outbound_lines_item_id
        """
    )
    op.execute(
        """
        ALTER INDEX IF EXISTS uq_internal_outbound_lines_doc_line_no
        RENAME TO uq_manual_outbound_lines_doc_line_no
        """
    )

    op.execute(
        """
        ALTER TABLE manual_outbound_lines
        RENAME CONSTRAINT fk_internal_outbound_lines_doc_id TO fk_manual_outbound_lines_doc_id
        """
    )
    op.execute(
        """
        ALTER TABLE manual_outbound_lines
        RENAME CONSTRAINT fk_internal_outbound_lines_item_id TO fk_manual_outbound_lines_item_id
        """
    )
    op.execute(
        """
        ALTER TABLE manual_outbound_docs
        RENAME CONSTRAINT fk_internal_outbound_docs_warehouse_id TO fk_manual_outbound_docs_warehouse_id
        """
    )
    op.execute(
        """
        ALTER TABLE manual_outbound_docs
        RENAME CONSTRAINT fk_internal_outbound_docs_recipient_id TO fk_manual_outbound_docs_recipient_id
        """
    )
    op.execute(
        """
        ALTER TABLE manual_outbound_docs
        RENAME CONSTRAINT fk_internal_outbound_docs_created_by TO fk_manual_outbound_docs_created_by
        """
    )
    op.execute(
        """
        ALTER TABLE manual_outbound_docs
        RENAME CONSTRAINT fk_internal_outbound_docs_confirmed_by TO fk_manual_outbound_docs_released_by
        """
    )
    op.execute(
        """
        ALTER TABLE manual_outbound_docs
        RENAME CONSTRAINT fk_internal_outbound_docs_canceled_by TO fk_manual_outbound_docs_voided_by
        """
    )


def downgrade() -> None:
    op.rename_table("manual_outbound_docs", "internal_outbound_docs")
    op.rename_table("manual_outbound_lines", "internal_outbound_lines")

    op.execute(
        """
        ALTER INDEX IF EXISTS ix_manual_outbound_docs_status
        RENAME TO ix_internal_outbound_docs_status
        """
    )
    op.execute(
        """
        ALTER INDEX IF EXISTS ix_manual_outbound_docs_trace_id
        RENAME TO ix_internal_outbound_docs_trace_id
        """
    )
    op.execute(
        """
        ALTER INDEX IF EXISTS ix_manual_outbound_docs_warehouse_doc_no
        RENAME TO ix_internal_outbound_docs_warehouse_doc_no
        """
    )
    op.execute(
        """
        ALTER INDEX IF EXISTS ix_manual_outbound_lines_doc_id
        RENAME TO ix_internal_outbound_lines_doc_id
        """
    )
    op.execute(
        """
        ALTER INDEX IF EXISTS ix_manual_outbound_lines_item_id
        RENAME TO ix_internal_outbound_lines_item_id
        """
    )
    op.execute(
        """
        ALTER INDEX IF EXISTS uq_manual_outbound_lines_doc_line_no
        RENAME TO uq_internal_outbound_lines_doc_line_no
        """
    )

    op.execute(
        """
        ALTER TABLE internal_outbound_lines
        RENAME CONSTRAINT fk_manual_outbound_lines_doc_id TO fk_internal_outbound_lines_doc_id
        """
    )
    op.execute(
        """
        ALTER TABLE internal_outbound_lines
        RENAME CONSTRAINT fk_manual_outbound_lines_item_id TO fk_internal_outbound_lines_item_id
        """
    )
    op.execute(
        """
        ALTER TABLE internal_outbound_docs
        RENAME CONSTRAINT fk_manual_outbound_docs_warehouse_id TO fk_internal_outbound_docs_warehouse_id
        """
    )
    op.execute(
        """
        ALTER TABLE internal_outbound_docs
        RENAME CONSTRAINT fk_manual_outbound_docs_recipient_id TO fk_internal_outbound_docs_recipient_id
        """
    )
    op.execute(
        """
        ALTER TABLE internal_outbound_docs
        RENAME CONSTRAINT fk_manual_outbound_docs_created_by TO fk_internal_outbound_docs_created_by
        """
    )
    op.execute(
        """
        ALTER TABLE internal_outbound_docs
        RENAME CONSTRAINT fk_manual_outbound_docs_released_by TO fk_internal_outbound_docs_confirmed_by
        """
    )
    op.execute(
        """
        ALTER TABLE internal_outbound_docs
        RENAME CONSTRAINT fk_manual_outbound_docs_voided_by TO fk_internal_outbound_docs_canceled_by
        """
    )
