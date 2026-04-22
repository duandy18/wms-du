"""repair wms_events source_type for count post

Revision ID: 20260422174415
Revises: 11c7f84c84b0
Create Date: 2026-04-22 17:44:15

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260422174415"
down_revision: Union[str, Sequence[str], None] = "11c7f84c84b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE wms_events
        DROP CONSTRAINT IF EXISTS ck_wms_events_source_type
        """
    )
    op.execute(
        """
        ALTER TABLE wms_events
        ADD CONSTRAINT ck_wms_events_source_type
        CHECK (
          source_type IN (
            'PURCHASE_ORDER',
            'MANUAL',
            'RETURN',
            'TRANSFER_IN',
            'ADJUST_IN',
            'ORDER',
            'ORDER_SHIP',
            'INTERNAL_OUTBOUND',
            'TRANSFER_OUT',
            'SCRAP',
            'ADJUST_OUT',
            'COUNT_TASK',
            'MANUAL_COUNT'
          )
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE wms_events
        DROP CONSTRAINT IF EXISTS ck_wms_events_source_type
        """
    )
    op.execute(
        """
        ALTER TABLE wms_events
        ADD CONSTRAINT ck_wms_events_source_type
        CHECK (
          source_type IN (
            'PURCHASE_ORDER',
            'MANUAL',
            'RETURN',
            'TRANSFER_IN',
            'ADJUST_IN',
            'ORDER'
          )
        )
        """
    )
