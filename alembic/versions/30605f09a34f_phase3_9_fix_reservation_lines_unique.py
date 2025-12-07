"""phase3_9_fix_reservation_lines_unique

把 reservation_lines 上的 (reservation_id, ref_line) 约束统一成一个唯一约束，
消除 alembic check 中关于 add_constraint 的 drift。
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "30605f09a34f"
down_revision: Union[str, Sequence[str], None] = "59ba81265708"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop old index (如果有的话)，然后加唯一约束。"""

    # 旧世界可能留下了一个普通索引，用同一个名字；
    # 如果这个索引存在，先删掉，避免名字冲突。
    op.execute(
        "DROP INDEX IF EXISTS ix_reservation_lines_res_refline;"
    )

    # 再加上我们真正想要的唯一约束
    op.execute(
        """
        ALTER TABLE reservation_lines
        ADD CONSTRAINT ix_reservation_lines_res_refline
        UNIQUE (reservation_id, ref_line);
        """
    )


def downgrade() -> None:
    """回滚：删唯一约束，视情况恢复普通索引。"""

    op.execute(
        """
        ALTER TABLE reservation_lines
        DROP CONSTRAINT IF EXISTS ix_reservation_lines_res_refline;
        """
    )

    # 如果你希望降级后保留一个普通索引，可以解开下面这一行：
    # op.execute(
    #     "CREATE INDEX IF NOT EXISTS ix_reservation_lines_res_refline "
    #     "ON reservation_lines (reservation_id, ref_line);"
    # )
