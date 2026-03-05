"""mc_bindings_current_only

Revision ID: 92974195e7fc
Revises: 7ef1d38c7242
Create Date: 2026-02-10 20:18:34.171864

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "92974195e7fc"
down_revision: Union[str, Sequence[str], None] = "7ef1d38c7242"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(conn, table: str, col: str) -> bool:
    row = conn.execute(
        sa.text(
            """
            SELECT 1
              FROM information_schema.columns
             WHERE table_schema = current_schema()
               AND table_name = :t
               AND column_name = :c
             LIMIT 1
            """
        ),
        {"t": table, "c": col},
    ).first()
    return row is not None


def _has_index(conn, index_name: str) -> bool:
    # PostgreSQL: pg_indexes
    row = conn.execute(
        sa.text(
            """
            SELECT 1
              FROM pg_indexes
             WHERE schemaname = current_schema()
               AND indexname = :i
             LIMIT 1
            """
        ),
        {"i": index_name},
    ).first()
    return row is not None


def _has_constraint(conn, table: str, constraint_name: str) -> bool:
    row = conn.execute(
        sa.text(
            """
            SELECT 1
              FROM information_schema.table_constraints
             WHERE table_schema = current_schema()
               AND table_name = :t
               AND constraint_name = :c
             LIMIT 1
            """
        ),
        {"t": table, "c": constraint_name},
    ).first()
    return row is not None


def upgrade() -> None:
    conn = op.get_bind()

    # 0) 表不存在则直接返回（保持幂等，避免 dev 库手工改动导致炸迁移）
    exists = conn.execute(
        sa.text(
            """
            SELECT 1
              FROM information_schema.tables
             WHERE table_schema = current_schema()
               AND table_name = 'merchant_code_fsku_bindings'
             LIMIT 1
            """
        )
    ).first()
    if not exists:
        return

    # 1) 增加 updated_at（先 nullable 便于回填）
    if not _has_column(conn, "merchant_code_fsku_bindings", "updated_at"):
        op.add_column(
            "merchant_code_fsku_bindings",
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    # 2) 删除历史行：只保留 current（effective_to IS NULL）
    if _has_column(conn, "merchant_code_fsku_bindings", "effective_to"):
        op.execute(sa.text("DELETE FROM merchant_code_fsku_bindings WHERE effective_to IS NOT NULL"))

    # 3) 回填 updated_at（用 created_at）
    op.execute(
        sa.text(
            "UPDATE merchant_code_fsku_bindings "
            "   SET updated_at = created_at "
            " WHERE updated_at IS NULL"
        )
    )

    # 4) 删除旧索引/约束（如果存在）
    # 4.1) drop partial unique index
    if _has_index(conn, "ux_mc_fsku_bindings_current"):
        op.execute(sa.text("DROP INDEX IF EXISTS ux_mc_fsku_bindings_current"))

    # 4.2) drop lookup index（alembic 可能会报不存在，所以先判断）
    if _has_index(conn, "ix_mc_fsku_bindings_lookup"):
        op.drop_index("ix_mc_fsku_bindings_lookup", table_name="merchant_code_fsku_bindings")

    # 5) 删除 time-ranged 字段
    if _has_column(conn, "merchant_code_fsku_bindings", "effective_from"):
        op.drop_column("merchant_code_fsku_bindings", "effective_from")
    if _has_column(conn, "merchant_code_fsku_bindings", "effective_to"):
        op.drop_column("merchant_code_fsku_bindings", "effective_to")

    # 6) updated_at 改为 NOT NULL
    op.alter_column(
        "merchant_code_fsku_bindings",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )

    # 7) 新的一码一对一约束
    if not _has_constraint(conn, "merchant_code_fsku_bindings", "ux_mc_fsku_bindings_unique"):
        op.create_unique_constraint(
            "ux_mc_fsku_bindings_unique",
            "merchant_code_fsku_bindings",
            ["platform", "shop_id", "merchant_code"],
        )

    # 8) 新 lookup 索引（不带 effective_to）
    if not _has_index(conn, "ix_mc_fsku_bindings_lookup"):
        op.create_index(
            "ix_mc_fsku_bindings_lookup",
            "merchant_code_fsku_bindings",
            ["platform", "shop_id", "merchant_code"],
            unique=False,
        )


def downgrade() -> None:
    conn = op.get_bind()

    exists = conn.execute(
        sa.text(
            """
            SELECT 1
              FROM information_schema.tables
             WHERE table_schema = current_schema()
               AND table_name = 'merchant_code_fsku_bindings'
             LIMIT 1
            """
        )
    ).first()
    if not exists:
        return

    # 1) drop new lookup index / unique constraint
    if _has_index(conn, "ix_mc_fsku_bindings_lookup"):
        op.drop_index("ix_mc_fsku_bindings_lookup", table_name="merchant_code_fsku_bindings")

    if _has_constraint(conn, "merchant_code_fsku_bindings", "ux_mc_fsku_bindings_unique"):
        op.drop_constraint("ux_mc_fsku_bindings_unique", "merchant_code_fsku_bindings", type_="unique")

    # 2) add back time-ranged columns（不恢复历史，仅恢复字段形态）
    if not _has_column(conn, "merchant_code_fsku_bindings", "effective_from"):
        op.add_column(
            "merchant_code_fsku_bindings",
            sa.Column(
                "effective_from",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )
        # 回填：用 created_at（更符合语义）
        op.execute(sa.text("UPDATE merchant_code_fsku_bindings SET effective_from = created_at"))

        # 去掉默认（保持和原表一致：应用层写入）
        op.alter_column(
            "merchant_code_fsku_bindings",
            "effective_from",
            existing_type=sa.DateTime(timezone=True),
            server_default=None,
        )

    if not _has_column(conn, "merchant_code_fsku_bindings", "effective_to"):
        op.add_column(
            "merchant_code_fsku_bindings",
            sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        )

    # 3) recreate old lookup index（含 effective_to）
    if not _has_index(conn, "ix_mc_fsku_bindings_lookup"):
        op.create_index(
            "ix_mc_fsku_bindings_lookup",
            "merchant_code_fsku_bindings",
            ["platform", "shop_id", "merchant_code", "effective_to"],
            unique=False,
        )

    # 4) recreate partial unique index（current 唯一）
    if not _has_index(conn, "ux_mc_fsku_bindings_current"):
        op.execute(
            sa.text(
                "CREATE UNIQUE INDEX ux_mc_fsku_bindings_current "
                "ON merchant_code_fsku_bindings(platform, shop_id, merchant_code) "
                "WHERE effective_to IS NULL"
            )
        )

    # 5) drop updated_at
    if _has_column(conn, "merchant_code_fsku_bindings", "updated_at"):
        op.drop_column("merchant_code_fsku_bindings", "updated_at")
