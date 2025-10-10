"""
stocks 补强：去重 → 唯一(item_id, location_id) → 非负保护 + 索引
- 合并历史重复 (item_id, location_id)
- 统一列名 qty -> quantity（若存在）
- SQLite: 唯一索引 + 触发器模拟 CHECK
- PostgreSQL: UNIQUE + CHECK
- 创建前做存在性探测
"""

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

revision = "20251006_stocks_constraints"
down_revision = "1f2c758faee3"  # ← 你仓库中上一版迁移ID
branch_labels = None
depends_on = None


def _col_exists(conn, table, col):
    return any(c["name"] == col for c in sa.inspect(conn).get_columns(table))


def _ix_exists(conn, table, name):
    try:
        return any(ix["name"] == name for ix in sa.inspect(conn).get_indexes(table))
    except Exception:
        return False


def _drop_trigger_if_exists(conn, name):
    conn.execute(text(f"DROP TRIGGER IF EXISTS {name};"))


def _dedupe_sqlite(conn):
    conn.execute(text("DELETE FROM stocks WHERE item_id IS NULL OR location_id IS NULL;"))
    conn.execute(
        text(
            """
        CREATE TEMP TABLE _agg AS
        SELECT item_id, location_id, SUM(COALESCE(quantity,0)) AS qty_sum, MIN(id) AS keep_id
        FROM stocks GROUP BY item_id, location_id;
    """
        )
    )
    conn.execute(
        text(
            """
        UPDATE stocks SET quantity = (SELECT qty_sum FROM _agg WHERE _agg.keep_id = stocks.id)
        WHERE id IN (SELECT keep_id FROM _agg);
    """
        )
    )
    conn.execute(
        text(
            """
        DELETE FROM stocks WHERE id IN (
          SELECT s.id FROM stocks s
          JOIN _agg a ON s.item_id=a.item_id AND s.location_id=a.location_id
          WHERE s.id <> a.keep_id
        );
    """
        )
    )
    conn.execute(text("DROP TABLE IF EXISTS _agg;"))


def _dedupe_postgres(conn):
    conn.execute(text("DELETE FROM stocks WHERE item_id IS NULL OR location_id IS NULL;"))
    conn.execute(
        text(
            """
        WITH summed AS (
          SELECT item_id, location_id, SUM(COALESCE(quantity,0)) AS qty_sum, MIN(id) AS keep_id
          FROM stocks GROUP BY item_id, location_id
        )
        UPDATE stocks s SET quantity = summed.qty_sum
        FROM summed WHERE s.id = summed.keep_id;
    """
        )
    )
    conn.execute(
        text(
            """
        DELETE FROM stocks s USING (
          SELECT item_id, location_id, MIN(id) AS keep_id
          FROM stocks GROUP BY item_id, location_id
        ) k
        WHERE s.item_id=k.item_id AND s.location_id=k.location_id AND s.id<>k.keep_id;
    """
        )
    )


def upgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name

    # 0) 兼容旧列名：qty -> quantity
    if _col_exists(conn, "stocks", "qty") and not _col_exists(conn, "stocks", "quantity"):
        if dialect == "sqlite":
            with op.batch_alter_table("stocks") as b:
                b.alter_column("qty", new_column_name="quantity")
        else:
            op.alter_column("stocks", "qty", new_column_name="quantity")

    # 1) 去重
    if dialect == "sqlite":
        _dedupe_sqlite(conn)
    else:
        _dedupe_postgres(conn)

    # 2) 约束与索引
    if dialect == "sqlite":
        if not _ix_exists(conn, "stocks", "ux_stocks_item_location"):
            op.create_index(
                "ux_stocks_item_location", "stocks", ["item_id", "location_id"], unique=True
            )
        if not _ix_exists(conn, "stocks", "ix_stocks_item"):
            op.create_index("ix_stocks_item", "stocks", ["item_id"])
        if not _ix_exists(conn, "stocks", "ix_stocks_location"):
            op.create_index("ix_stocks_location", "stocks", ["location_id"])

        _drop_trigger_if_exists(conn, "stocks_ck_non_negative_ins")
        _drop_trigger_if_exists(conn, "stocks_ck_non_negative_upd")

        conn.execute(
            text(
                """
            CREATE TRIGGER stocks_ck_non_negative_ins
            BEFORE INSERT ON stocks
            FOR EACH ROW
            WHEN NEW.quantity < 0
            BEGIN
              SELECT RAISE(ABORT, 'quantity must be non-negative');
            END;
        """
            )
        )
        conn.execute(
            text(
                """
            CREATE TRIGGER stocks_ck_non_negative_upd
            BEFORE UPDATE OF quantity ON stocks
            FOR EACH ROW
            WHEN NEW.quantity < 0
            BEGIN
              SELECT RAISE(ABORT, 'quantity must be non-negative');
            END;
        """
            )
        )
    else:
        # PG: UNIQUE + CHECK + 索引（尽量容错）
        try:
            op.create_unique_constraint(
                "uq_stocks_item_location", "stocks", ["item_id", "location_id"]
            )
        except Exception:
            pass
        try:
            op.create_check_constraint("ck_stocks_non_negative", "stocks", "quantity >= 0")
        except Exception:
            pass
        if not _ix_exists(conn, "stocks", "ix_stocks_item"):
            op.create_index("ix_stocks_item", "stocks", ["item_id"])
        if not _ix_exists(conn, "stocks", "ix_stocks_location"):
            op.create_index("ix_stocks_location", "stocks", ["location_id"])


def downgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect == "sqlite":
        _drop_trigger_if_exists(conn, "stocks_ck_non_negative_ins")
        _drop_trigger_if_exists(conn, "stocks_ck_non_negative_upd")
        if _ix_exists(conn, "stocks", "ix_stocks_location"):
            op.drop_index("ix_stocks_location", table_name="stocks")
        if _ix_exists(conn, "stocks", "ix_stocks_item"):
            op.drop_index("ix_stocks_item", table_name="stocks")
        if _ix_exists(conn, "stocks", "ux_stocks_item_location"):
            op.drop_index("ux_stocks_item_location", table_name="stocks")
    else:
        for act in (
            lambda: op.drop_index("ix_stocks_location", table_name="stocks"),
            lambda: op.drop_index("ix_stocks_item", table_name="stocks"),
            lambda: op.drop_constraint("ck_stocks_non_negative", "stocks", type_="check"),
            lambda: op.drop_constraint("uq_stocks_item_location", "stocks", type_="unique"),
        ):
            try:
                act()
            except Exception:
                pass

    # 可选：列名还原
    if _col_exists(conn, "stocks", "quantity") and not _col_exists(conn, "stocks", "qty"):
        if dialect == "sqlite":
            with op.batch_alter_table("stocks") as b:
                b.alter_column("quantity", new_column_name="qty")
        else:
            op.alter_column("stocks", "quantity", new_column_name="qty")
