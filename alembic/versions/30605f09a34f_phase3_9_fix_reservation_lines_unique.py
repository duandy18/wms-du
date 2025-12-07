"""phase3_9_fix_reservation_lines_unique

Revision ID: 30605f09a34f
Revises: 59ba81265708
Create Date: 2025-11-16 16:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "30605f09a34f"
down_revision: Union[str, Sequence[str], None] = "59ba81265708"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_uc(bind, table: str, name: str) -> bool:
    sql = sa.text(
        """
        SELECT 1
          FROM pg_constraint c
          JOIN pg_class t ON t.oid = c.conrelid
         WHERE c.conname = :n
           AND c.contype = 'u'
           AND t.relname = :t
         LIMIT 1
        """
    )
    return bind.execute(sql, {"n": name, "t": table}).first() is not None


def upgrade() -> None:
    """Upgrade schema.

    目标：确保 reservation_lines 上唯一约束为 (reservation_id, ref_line)。

    说明：
    - 在 59ba... 中我们已经创建了
      UNIQUE CONSTRAINT ix_reservation_lines_res_refline(reservation_id, ref_line)；
    - 在这种情况下，本迁移对 reservation_lines 可以视为 NOOP；
    - 只有在该约束不存在的老环境里，才需要执行修正逻辑。
    """
    bind = op.get_bind()

    # 如果已经有了目标唯一约束，直接跳过（避免 DROP INDEX 把自己绊死）
    if _has_uc(bind, "reservation_lines", "ix_reservation_lines_res_refline"):
        return

    # 老逻辑：先删旧索引，再建唯一约束
    # 这里用 DO $$ 防御“索引已经被约束占用”的场景
    op.execute(
        """
        DO $$
        BEGIN
          BEGIN
            DROP INDEX IF EXISTS ix_reservation_lines_res_refline;
          EXCEPTION
            WHEN others THEN
              -- 如果因为依赖关系导致 DROP INDEX 失败，就忽略，后续用 UNIQUE CONSTRAINT 收口
              NULL;
          END;
        END$$;
        """
    )

    # 再补上统一的唯一约束（如果还不存在）
    if not _has_uc(bind, "reservation_lines", "ix_reservation_lines_res_refline"):
        op.create_unique_constraint(
            "ix_reservation_lines_res_refline",
            "reservation_lines",
            ["reservation_id", "ref_line"],
        )


def downgrade() -> None:
    """Downgrade schema.

    回滚时尽量恢复到“普通索引”形态。
    """
    bind = op.get_bind()

    if _has_uc(bind, "reservation_lines", "ix_reservation_lines_res_refline"):
        op.drop_constraint(
            "ix_reservation_lines_res_refline",
            "reservation_lines",
            type_="unique",
        )

    # 补一个普通索引（如果没有的话）
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
              FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE c.relkind = 'i'
               AND c.relname = 'ix_reservation_lines_res_refline'
               AND n.nspname = 'public'
          ) THEN
            CREATE INDEX ix_reservation_lines_res_refline
              ON reservation_lines (reservation_id, ref_line);
          END IF;
        END$$;
        """
    )
