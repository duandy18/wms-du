"""manual outbound schema cutover

Revision ID: d77c6eba9c7e
Revises: 9f320f159245
Create Date: 2026-04-20 11:41:20.908229

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d77c6eba9c7e"
down_revision: Union[str, Sequence[str], None] = "9f320f159245"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "manual_outbound_docs",
        "note",
        new_column_name="remark",
        existing_type=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "manual_outbound_docs",
        "confirmed_by",
        new_column_name="released_by",
        existing_type=sa.BigInteger(),
        existing_nullable=True,
    )
    op.alter_column(
        "manual_outbound_docs",
        "confirmed_at",
        new_column_name="released_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=True,
    )
    op.alter_column(
        "manual_outbound_docs",
        "canceled_by",
        new_column_name="voided_by",
        existing_type=sa.BigInteger(),
        existing_nullable=True,
    )
    op.alter_column(
        "manual_outbound_docs",
        "canceled_at",
        new_column_name="voided_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=True,
    )

    op.alter_column(
        "manual_outbound_lines",
        "note",
        new_column_name="remark",
        existing_type=sa.Text(),
        existing_nullable=True,
    )
    op.drop_column("manual_outbound_lines", "batch_code")
    op.drop_column("manual_outbound_lines", "confirmed_qty")

    for name in (
        "internal_outbound_docs_created_by_fkey",
        "internal_outbound_docs_recipient_id_fkey",
        "internal_outbound_docs_confirmed_by_fkey",
        "internal_outbound_docs_canceled_by_fkey",
    ):
        try:
            op.drop_constraint(name, "manual_outbound_docs", type_="foreignkey")
        except Exception:
            pass

    op.execute(
        "ALTER SEQUENCE IF EXISTS internal_outbound_docs_id_seq "
        "RENAME TO manual_outbound_docs_id_seq"
    )
    op.execute(
        "ALTER SEQUENCE IF EXISTS internal_outbound_lines_id_seq "
        "RENAME TO manual_outbound_lines_id_seq"
    )

    try:
        op.execute(
            "ALTER TABLE manual_outbound_docs "
            "RENAME CONSTRAINT internal_outbound_docs_pkey TO manual_outbound_docs_pkey"
        )
    except Exception:
        pass

    try:
        op.execute(
            "ALTER TABLE manual_outbound_lines "
            "RENAME CONSTRAINT internal_outbound_lines_pkey TO manual_outbound_lines_pkey"
        )
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.execute(
            "ALTER TABLE manual_outbound_docs "
            "RENAME CONSTRAINT manual_outbound_docs_pkey TO internal_outbound_docs_pkey"
        )
    except Exception:
        pass

    try:
        op.execute(
            "ALTER TABLE manual_outbound_lines "
            "RENAME CONSTRAINT manual_outbound_lines_pkey TO internal_outbound_lines_pkey"
        )
    except Exception:
        pass

    op.execute(
        "ALTER SEQUENCE IF EXISTS manual_outbound_docs_id_seq "
        "RENAME TO internal_outbound_docs_id_seq"
    )
    op.execute(
        "ALTER SEQUENCE IF EXISTS manual_outbound_lines_id_seq "
        "RENAME TO internal_outbound_lines_id_seq"
    )

    op.add_column(
        "manual_outbound_lines",
        sa.Column("batch_code", sa.Text(), nullable=True),
    )
    op.add_column(
        "manual_outbound_lines",
        sa.Column("confirmed_qty", sa.Integer(), nullable=True),
    )
    op.alter_column(
        "manual_outbound_lines",
        "remark",
        new_column_name="note",
        existing_type=sa.Text(),
        existing_nullable=True,
    )

    op.alter_column(
        "manual_outbound_docs",
        "remark",
        new_column_name="note",
        existing_type=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "manual_outbound_docs",
        "released_by",
        new_column_name="confirmed_by",
        existing_type=sa.BigInteger(),
        existing_nullable=True,
    )
    op.alter_column(
        "manual_outbound_docs",
        "released_at",
        new_column_name="confirmed_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=True,
    )
    op.alter_column(
        "manual_outbound_docs",
        "voided_by",
        new_column_name="canceled_by",
        existing_type=sa.BigInteger(),
        existing_nullable=True,
    )
    op.alter_column(
        "manual_outbound_docs",
        "voided_at",
        new_column_name="canceled_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=True,
    )
