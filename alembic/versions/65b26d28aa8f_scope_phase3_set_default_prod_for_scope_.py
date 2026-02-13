"""scope phase3: set default PROD for scope columns

Revision ID: 65b26d28aa8f
Revises: de0ea3cf52ec
Create Date: 2026-02-13 15:13:36.367583
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "65b26d28aa8f"
down_revision: Union[str, Sequence[str], None] = "de0ea3cf52ec"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    兼容历史写入：
    - 若调用侧未显式传 scope，则默认落到 PROD 宇宙
    - 避免 NOT NULL 约束导致旧 INSERT 爆炸
    """
    op.execute("ALTER TABLE orders ALTER COLUMN scope SET DEFAULT 'PROD'")
    op.execute("ALTER TABLE pick_tasks ALTER COLUMN scope SET DEFAULT 'PROD'")
    op.execute("ALTER TABLE outbound_commits_v2 ALTER COLUMN scope SET DEFAULT 'PROD'")


def downgrade() -> None:
    op.execute("ALTER TABLE outbound_commits_v2 ALTER COLUMN scope DROP DEFAULT")
    op.execute("ALTER TABLE pick_tasks ALTER COLUMN scope DROP DEFAULT")
    op.execute("ALTER TABLE orders ALTER COLUMN scope DROP DEFAULT")
