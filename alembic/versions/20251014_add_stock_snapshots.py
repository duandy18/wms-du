"""add stock_snapshots for periodic inventory snapshots

Revision ID: 20251014_add_stock_snapshots
Revises:
Create Date: 2025-10-14
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20251014_add_stock_snapshots"
down_revision = None
branch_labels = None
depends_on = None


def _insp():
    bind = op.get_bind()
    return sa.inspect(bind)


def _has_table(name: str) -> bool:
    return name in _insp().get_table_names(schema=None)


def _has_index(table: str, index_name: str) -> bool:
    for ix in _insp().get_indexes(table):
        if ix.get("name") == index_name:
            return True
    return False


def _columns(table: str) -> set[str]:
    try:
        return {c["name"] for c in _insp().get_columns(table)}
    except Exception:
        return set()


def upgrade():
    """
    幂等&自适应：
    - 若表不存在：按“新方案”创建（as_of_ts）。
    - 若表已存在：不改表，仅创建缺失索引；索引中的时间列根据现有列名动态选择：
        优先 as_of_ts；没有则使用 snapshot_date。
    """
    table = "stock_snapshots"

    if not _has_table(table):
        op.create_table(
            table,
            sa.Column("id", sa.BigInteger, primary_key=True),
            sa.Column("as_of_ts", sa.DateTime(timezone=True), nullable=False),
            sa.Column("item_id", sa.BigInteger, nullable=False),
            sa.Column("location_id", sa.BigInteger, nullable=False),
            sa.Column("qty", sa.Numeric(18, 4), nullable=False, server_default=sa.text("0")),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "as_of_ts", "item_id", "location_id", name="uq_stock_snapshots_cut_item_loc"
            ),
        )

    # 动态选择时间列：as_of_ts 或 snapshot_date
    cols = _columns(table)
    ts_col = (
        "as_of_ts" if "as_of_ts" in cols else ("snapshot_date" if "snapshot_date" in cols else None)
    )

    if ts_col is None:
        # 极端情况：既没有 as_of_ts 也没有 snapshot_date（不应发生）
        # 宽松跳过索引创建，以免卡住整个迁移链
        return

    # 创建常用查询索引（若不存在）
    if not _has_index(table, "ix_stock_snapshots_item_loc_ts"):
        op.create_index(
            "ix_stock_snapshots_item_loc_ts",
            table,
            ["item_id", "location_id", ts_col],
            unique=False,
        )


def downgrade():
    table = "stock_snapshots"
    try:
        op.drop_index("ix_stock_snapshots_item_loc_ts", table_name=table)
    except Exception:
        pass
    try:
        op.drop_table(table)
    except Exception:
        pass
