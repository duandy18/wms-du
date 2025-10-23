"""add/ensure constraints & indexes on stocks (safe if table missing)

Revision ID: 20251006_add_constraints_to_stocks
Revises: f995a82ac74e
Create Date: 2025-10-06 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import text  # 新增：用于执行原生 SQL
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251006_add_constraints_to_stocks"
down_revision: str | Sequence[str] | None = "f995a82ac74e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        return insp.has_table(name)  # 一些方言支持
    except Exception:
        return name in insp.get_table_names()


def _index_names(table: str) -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        return {ix["name"] for ix in insp.get_indexes(table)}
    except Exception:
        return set()


def _unique_names(table: str) -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        return {uc["name"] for uc in insp.get_unique_constraints(table)}
    except Exception:
        return set()


def _widen_alembic_version_if_needed() -> None:
    """
    在 PostgreSQL 上将 alembic_version.version_num 扩展到 VARCHAR(255)，
    仅当当前长度 < 64 时执行；SQLite 的 TEXT 无需处理。
    这样保证后续长 revision_id（如 '20251006_add_constraints_to_stocks'）不会触发截断错误。
    """
    bind = op.get_bind()
    dialect = (bind.dialect.name or "").lower()
    if dialect != "postgresql":
        return

    # 读取当前列宽
    maxlen = bind.execute(
        text(
            """
            SELECT character_maximum_length
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='alembic_version' AND column_name='version_num'
            """
        )
    ).scalar()

    try:
        current = int(maxlen) if maxlen is not None else None
    except Exception:
        current = None

    # 仅当列宽未知或小于 64（明显不足以容纳长 revision id）时才加宽
    if current is None or current < 64:
        bind.execute(text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"))


def upgrade() -> None:
    # 预处理：在干净环境（CI）里先加宽 alembic_version.version_num，避免后续长 revision id 触发截断
    _widen_alembic_version_if_needed()

    # 1) 若 stocks 不存在，先创建“最小可用”结构（PG/SQLite 通用）
    if not _has_table("stocks"):
        op.create_table(
            "stocks",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("item_id", sa.Integer(), nullable=False),
            sa.Column("location_id", sa.Integer(), nullable=False),
            sa.Column("qty", sa.Integer(), nullable=False, server_default=sa.text("0")),
        )

    # 2) 幂等补约束/索引
    uqs = _unique_names("stocks")
    idx = _index_names("stocks")

    if "uq_stocks_item_location" not in uqs:
        op.create_unique_constraint(
            "uq_stocks_item_location",
            "stocks",
            ["item_id", "location_id"],
        )

    if "ix_stocks_item" not in idx:
        op.create_index("ix_stocks_item", "stocks", ["item_id"], unique=False)

    if "ix_stocks_location" not in idx:
        op.create_index("ix_stocks_location", "stocks", ["location_id"], unique=False)

    # 热点联合索引（查询 item+location）
    if "ix_stock_item_loc" not in idx:
        op.create_index("ix_stock_item_loc", "stocks", ["item_id", "location_id"], unique=False)


def downgrade() -> None:
    # 只撤销本迁移创建的对象；不删除表结构
    idx = _index_names("stocks")
    uqs = _unique_names("stocks")

    if "ix_stock_item_loc" in idx:
        op.drop_index("ix_stock_item_loc", table_name="stocks")

    if "ix_stocks_location" in idx:
        op.drop_index("ix_stocks_location", table_name="stocks")

    if "ix_stocks_item" in idx:
        op.drop_index("ix_stocks_item", table_name="stocks")

    if "uq_stocks_item_location" in uqs:
        op.drop_constraint("uq_stocks_item_location", "stocks", type_="unique")
