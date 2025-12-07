"""order_items: item_id nullable + FK ON DELETE SET NULL

Revision ID: 8fdf6551cc08
Revises: 973f5eea107b
Create Date: 2025-11-07 17:05:19.864161
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "8fdf6551cc08"
down_revision: Union[str, Sequence[str], None] = "973f5eea107b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FK_NAME = "fk_order_items_item_id_items"


def _has_fk(bind, table: str, name: str) -> bool:
    insp = sa.inspect(bind)
    return any(fk.get("name") == name for fk in insp.get_foreign_keys(table))


def _col_is_not_null(bind, table: str, col: str) -> bool:
    row = bind.execute(
        sa.text(
            """
            SELECT is_nullable
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=:t AND column_name=:c
            """
        ),
        {"t": table, "c": col},
    ).first()
    return bool(row and row[0] == "NO")


def upgrade() -> None:
    bind = op.get_bind()

    # 1) 若存在旧外键（可能不是 SET NULL），先移除
    if _has_fk(bind, "order_items", _FK_NAME):
        bind.execute(sa.text(f"ALTER TABLE order_items DROP CONSTRAINT {_FK_NAME}"))

    # 2) 将 item_id 改为可空（如果目前是 NOT NULL）
    if _col_is_not_null(bind, "order_items", "item_id"):
        bind.execute(sa.text("ALTER TABLE order_items ALTER COLUMN item_id DROP NOT NULL"))

    # 3) 重新创建外键为 ON DELETE SET NULL
    bind.execute(
        sa.text(
            f"""
            ALTER TABLE order_items
            ADD CONSTRAINT {_FK_NAME}
            FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE SET NULL
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()

    # 回滚：删掉 SET NULL 外键，恢复 NOT NULL（谨慎处理）
    if _has_fk(bind, "order_items", _FK_NAME):
        bind.execute(sa.text(f"ALTER TABLE order_items DROP CONSTRAINT {_FK_NAME}"))

    # 如需强行回滚为 NOT NULL（仅在不存在 NULL 时）
    # bind.execute(sa.text("ALTER TABLE order_items ALTER COLUMN item_id SET NOT NULL"))
    # bind.execute(sa.text("""
    #     ALTER TABLE order_items
    #     ADD CONSTRAINT fk_order_items_item_id_items
    #     FOREIGN KEY (item_id) REFERENCES items(id)
    # """))
