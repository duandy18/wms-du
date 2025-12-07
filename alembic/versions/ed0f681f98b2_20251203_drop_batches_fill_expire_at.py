"""20251203_drop_batches_fill_expire_at

Revision ID: ed0f681f98b2
Revises: clean_stocks_legacy_fields
Create Date: 2025-12-03 14:38:58.383543

"""
from typing import Sequence, Union
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ed0f681f98b2"
down_revision: Union[str, Sequence[str], None] = "clean_stocks_legacy_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove legacy trigger + function which reference the removed expire_at column."""
    # 删除触发器（如果存在）
    op.execute(
        "DROP TRIGGER IF EXISTS trg_batches_fill_expire_at ON batches;"
    )

    # 删除触发器对应函数（如果存在）
    op.execute(
        "DROP FUNCTION IF EXISTS batches_fill_expire_at();"
    )


def downgrade() -> None:
    """Recreate a no-op trigger + function (does nothing, avoids referencing old expire_at)."""
    # 恢复一个空函数（不会访问不存在的 expire_at 字段）
    op.execute(
        """
        CREATE FUNCTION batches_fill_expire_at()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            -- old logic referenced NEW.expire_at which no longer exists.
            -- this downgraded replacement does nothing.
            RETURN NEW;
        END;
        $$;
        """
    )

    # 恢复触发器，指向这个空函数
    op.execute(
        """
        CREATE TRIGGER trg_batches_fill_expire_at
        BEFORE INSERT OR UPDATE ON batches
        FOR EACH ROW
        EXECUTE FUNCTION batches_fill_expire_at();
        """
    )
