"""fix platform_order_manual_decisions id default sequence

Revision ID: 51d23f377b32
Revises: a3bc8a90d180
Create Date: 2026-02-09 17:35:06.913909
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "51d23f377b32"
down_revision: Union[str, Sequence[str], None] = "a3bc8a90d180"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 幂等修复：确保 id 有 sequence default；即使已存在也不会破坏
    op.execute(
        """
        DO $$
        BEGIN
            -- sequence 不存在就创建
            IF NOT EXISTS (
                SELECT 1 FROM pg_class WHERE relname = 'platform_order_manual_decisions_id_seq'
            ) THEN
                CREATE SEQUENCE platform_order_manual_decisions_id_seq;
                ALTER SEQUENCE platform_order_manual_decisions_id_seq
                    OWNED BY platform_order_manual_decisions.id;
            END IF;

            -- 设置默认值（若已设置则无影响）
            ALTER TABLE platform_order_manual_decisions
                ALTER COLUMN id SET DEFAULT nextval('platform_order_manual_decisions_id_seq');

            -- sequence 起始值对齐现有数据（避免未来插入碰撞；空表也安全）
            PERFORM setval(
                'platform_order_manual_decisions_id_seq',
                COALESCE((SELECT MAX(id) FROM platform_order_manual_decisions), 0) + 1,
                false
            );
        END $$;
        """
    )


def downgrade() -> None:
    # 回滚只撤 default，不强删 sequence（避免误伤已被其它对象依赖）
    op.execute(
        """
        ALTER TABLE platform_order_manual_decisions
            ALTER COLUMN id DROP DEFAULT;
        """
    )
