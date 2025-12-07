"""normalize reservations schema: drop NOT NULL on legacy cols + add uq(platform,shop_id,ref)

Revision ID: 21fcb6145817
Revises: 789cdd39f75f
Create Date: 2025-11-08 06:52:07.329898
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "21fcb6145817"
down_revision: Union[str, Sequence[str], None] = "789cdd39f75f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UQ = "uq_reservations_platform_shop_ref"


def _has_column(bind, table: str, col: str) -> bool:
    row = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=:t AND column_name=:c
            LIMIT 1
            """
        ),
        {"t": table, "c": col},
    ).first()
    return row is not None


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


def _has_constraint(bind, table: str, conname: str) -> bool:
    row = bind.execute(
        sa.text(
            """
            SELECT 1 FROM pg_constraint
            WHERE conname=:n AND conrelid=('public.'||:t)::regclass
            LIMIT 1
            """
        ),
        {"n": conname, "t": table},
    ).first()
    return row is not None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    # 1) 确保合同字段存在（不存在则补列）
    must_cols = [
        ("platform", "VARCHAR(32)"),
        ("shop_id", "VARCHAR(128)"),
        ("ref", "VARCHAR(256)"),
        ("warehouse_id", "INTEGER"),
        ("status", "VARCHAR(16)"),
        ("created_at", "TIMESTAMPTZ"),
    ]
    for col, ddl in must_cols:
        if not _has_column(bind, "reservations", col):
            bind.execute(sa.text(f"ALTER TABLE reservations ADD COLUMN {col} {ddl}"))

    # 2) 回填缺省，避免后续 SET NOT NULL/唯一时报 NULL
    bind.execute(sa.text("UPDATE reservations SET platform     = COALESCE(platform, 'LEGACY')"))
    bind.execute(sa.text("UPDATE reservations SET shop_id      = COALESCE(shop_id , 'NO-STORE')"))
    bind.execute(
        sa.text("UPDATE reservations SET ref          = COALESCE(ref     , 'LEGACY-'||id::text)")
    )
    bind.execute(sa.text("UPDATE reservations SET warehouse_id = COALESCE(warehouse_id, 0)"))
    bind.execute(sa.text("UPDATE reservations SET status       = COALESCE(status, 'PLANNED')"))
    bind.execute(sa.text("UPDATE reservations SET created_at   = COALESCE(created_at, now())"))
    # 2.1 若存在历史 qty 列，先全部回填为 0（以便能够去掉 NOT NULL）
    if _has_column(bind, "reservations", "qty"):
        bind.execute(sa.text("UPDATE reservations SET qty = COALESCE(qty, 0)"))

    # 3) 历史怪列：若存在且 NOT NULL，则解除 NOT NULL 约束（不删列，保持兼容）
    for legacy in ("item_id", "location_id", "batch_id", "qty"):
        if _has_column(bind, "reservations", legacy) and _col_is_not_null(
            bind, "reservations", legacy
        ):
            bind.execute(sa.text(f"ALTER TABLE reservations ALTER COLUMN {legacy} DROP NOT NULL"))

    # 4) 固化合同字段为 NOT NULL + 默认
    bind.execute(sa.text("ALTER TABLE reservations ALTER COLUMN platform     SET NOT NULL"))
    bind.execute(sa.text("ALTER TABLE reservations ALTER COLUMN shop_id      SET NOT NULL"))
    bind.execute(sa.text("ALTER TABLE reservations ALTER COLUMN ref          SET NOT NULL"))
    bind.execute(sa.text("ALTER TABLE reservations ALTER COLUMN warehouse_id SET NOT NULL"))
    bind.execute(sa.text("ALTER TABLE reservations ALTER COLUMN status       SET NOT NULL"))
    bind.execute(sa.text("ALTER TABLE reservations ALTER COLUMN created_at   SET NOT NULL"))
    bind.execute(
        sa.text("ALTER TABLE reservations ALTER COLUMN status       SET DEFAULT 'PLANNED'")
    )

    # 5) 幂等唯一键：(platform, shop_id, ref)
    if not _has_constraint(bind, "reservations", _UQ):
        bind.execute(
            sa.text(
                f"ALTER TABLE reservations ADD CONSTRAINT {_UQ} UNIQUE (platform, shop_id, ref)"
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    # 仅撤销唯一和默认，不恢复历史 NOT NULL（避免破坏清洗后数据）
    if _has_constraint(bind, "reservations", _UQ):
        bind.execute(sa.text(f"ALTER TABLE reservations DROP CONSTRAINT {_UQ}"))
    bind.execute(sa.text("ALTER TABLE IF EXISTS reservations ALTER COLUMN status DROP DEFAULT"))
