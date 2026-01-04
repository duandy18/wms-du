"""merge heads: ledger_unique_ref + set_comment_expire_at

Revision ID: 7f303f46e944
Revises: 20251112_ledger_unique_ref_item_wh_batch_neg, 20251112_set_comment_on_batches_expire_at
Create Date: 2025-11-12 15:27:12.825341

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = '7f303f46e944'
down_revision: Union[str, Sequence[str], None] = ('20251112_ledger_unique_ref_item_wh_batch_neg', '20251112_set_comment_on_batches_expire_at')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
