"""create platform_shops (Phase 2.7) — idempotent & safe

改动要点：
- upgrade(): 若已存在 `platform_shops` 表则跳过建表；索引不存在才创建
- downgrade(): 若有则删索引；若表存在再删表（幂等回滚）
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection
from sqlalchemy import inspect, text


# 维持你仓库既有 revision/链路；如需衔接到特定父修订，请自行调整
revision = "2_7_010_create_platform_shops"
down_revision = None  # ← 若你的链路需要，改成上一版的 revision id
branch_labels = None
depends_on = None


def _is_sqlite(conn: Connection) -> bool:
    return conn.dialect.name == "sqlite"


def _index_exists(conn: Connection, index_name: str, table_name: str) -> bool:
    """跨方言检查索引是否存在（最佳努力）"""
    dialect = conn.dialect.name
    if dialect == "postgresql":
        sql = text(
            "SELECT 1 FROM pg_indexes WHERE schemaname = current_schema() "
            "AND indexname = :idx AND tablename = :tbl"
        )
        return conn.execute(sql, {"idx": index_name, "tbl": table_name}).first() is not None
    elif dialect == "sqlite":
        # PRAGMA index_list 返回 (seq, name, unique, origin, partial, ..)
        rows = conn.exec_driver_sql(f'PRAGMA index_list("{table_name}")').all()
        return any(r[1] == index_name for r in rows)
    else:
        # 其它方言尽量通过 SQLAlchemy Inspector 兜底
        try:
            ix = inspect(conn).get_indexes(table_name)
            return any(i.get("name") == index_name for i in ix)
        except Exception:
            return False


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    sqlite = _is_sqlite(bind)

    table_name = "platform_shops"
    index_name = "ix_platform_shops_status"

    # 1) 表存在性保护：已存在则直接跳过建表
    if not insp.has_table(table_name):
        op.create_table(
            table_name,
            sa.Column(
                "id", sa.Integer if sqlite else sa.BigInteger, primary_key=True, autoincrement=True
            ),
            sa.Column("platform", sa.String(32), nullable=False),
            sa.Column("shop_id", sa.String(64), nullable=False),
            sa.Column("access_token", sa.Text, nullable=True),
            sa.Column("refresh_token", sa.Text, nullable=True),
            sa.Column(
                "token_expires_at",
                sa.TIMESTAMP(timezone=not sqlite),
                nullable=True,
            ),
            sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
            sa.Column("rate_limit_qps", sa.Integer, nullable=False, server_default="5"),
            sa.Column(
                "created_at",
                sa.TIMESTAMP(timezone=not sqlite),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP" if sqlite else "now()"),
            ),
            sa.Column(
                "updated_at",
                sa.TIMESTAMP(timezone=not sqlite),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP" if sqlite else "now()"),
            ),
            sa.UniqueConstraint("platform", "shop_id", name="uq_platform_shops_platform_shop"),
        )

    # 2) 索引存在性保护：不存在才创建
    if not _index_exists(bind, index_name, table_name):
        op.create_index(index_name, table_name, ["status"])


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)

    table_name = "platform_shops"
    index_name = "ix_platform_shops_status"

    # 先删索引（若存在）
    try:
        if _index_exists(bind, index_name, table_name):
            op.drop_index(index_name, table_name=table_name)
    except Exception:
        # 某些方言/历史状态下，索引删除失败不应阻断回滚
        pass

    # 再删表（若存在）
    if insp.has_table(table_name):
        op.drop_table(table_name)
