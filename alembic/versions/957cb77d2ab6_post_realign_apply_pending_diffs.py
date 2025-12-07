"""post-realign apply pending diffs

Revision ID: 957cb77d2ab6
Revises: 4c4d82a60a66
Create Date: 2025-11-09 20:43:05.601020
"""

from typing import Sequence, Union, List, Tuple

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "957cb77d2ab6"
down_revision: Union[str, Sequence[str], None] = "4c4d82a60a66"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# -------- helpers --------
def _capture_and_drop_views_depending_on(table_name: str) -> List[Tuple[str, str]]:
    """返回 [(view_name, viewdef SQL), ...] 并先 DROP 这些视图（IF EXISTS）。"""
    conn = op.get_bind()
    rows = conn.exec_driver_sql(
        """
        SELECT c.relname AS view_name,
               pg_get_viewdef(c.oid, true) AS viewdef
        FROM pg_depend d
        JOIN pg_rewrite r ON d.objid = r.oid
        JOIN pg_class   c ON r.ev_class = c.oid
        JOIN pg_class   t ON d.refobjid = t.oid
        WHERE c.relkind = 'v'
          AND t.relname = %(tbl)s
        GROUP BY c.relname, c.oid
        ORDER BY c.relname
        """,
        {"tbl": table_name},
    ).fetchall()

    captured: List[Tuple[str, str]] = []
    for view_name, viewdef in rows:
        if viewdef:
            captured.append((view_name, viewdef))
            op.execute(f'DROP VIEW IF EXISTS "{view_name}" CASCADE')
    return captured


def _recreate_views(captured: List[Tuple[str, str]]) -> None:
    for view_name, viewdef in captured:
        op.execute(f'CREATE OR REPLACE VIEW "{view_name}" AS {viewdef}')


def _drop_index_or_constraint_if_exists(name: str, table: str) -> None:
    """先删唯一约束，再删同名索引（幂等），避免依赖冲突。"""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint c
                JOIN pg_class rel ON rel.oid = c.conrelid
                WHERE c.contype='u' AND c.conname='{name}' AND rel.relname='{table}'
            ) THEN
                EXECUTE 'ALTER TABLE "{table}" DROP CONSTRAINT "{name}"';
            END IF;
        END $$;
        """
    )
    op.execute(f'DROP INDEX IF EXISTS "{name}"')


def _has_column(table: str, col: str) -> bool:
    bind = op.get_bind()
    sql = sa.text(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=:t AND column_name=:c
        LIMIT 1
        """
    )
    return bind.execute(sql, {"t": table, "c": col}).first() is not None


def _has_index(name: str) -> bool:
    bind = op.get_bind()
    sql = sa.text(
        """
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND indexname  = :n
        LIMIT 1
        """
    )
    return bind.execute(sql, {"n": name}).first() is not None


def upgrade() -> None:
    """Upgrade schema（with safety prelude）."""

    # -----------------------------
    # Safety prelude: 清洗 stocks（外键将补建）
    # -----------------------------
    op.execute(
        """
        DELETE FROM stocks s
        WHERE (item_id      IS NOT NULL AND NOT EXISTS (SELECT 1 FROM items      i WHERE i.id = s.item_id))
           OR (location_id  IS NOT NULL AND NOT EXISTS (SELECT 1 FROM locations  l WHERE l.id = s.location_id))
           OR (batch_id     IS NOT NULL AND NOT EXISTS (SELECT 1 FROM batches    b WHERE b.id = s.batch_id));
        """
    )

    # -----------------------------
    # event_error_log：新增列（临时默认 → 回填 → 非空 → 去默认）
    # -----------------------------
    op.add_column(
        "event_error_log",
        sa.Column("platform", sa.String(32), server_default=sa.text("''"), nullable=True),
    )
    op.add_column(
        "event_error_log",
        sa.Column("shop_id", sa.String(64), server_default=sa.text("''"), nullable=True),
    )
    op.add_column(
        "event_error_log",
        sa.Column("order_no", sa.String(128), server_default=sa.text("''"), nullable=True),
    )
    op.add_column(
        "event_error_log",
        sa.Column("idempotency_key", sa.String(256), server_default=sa.text("''"), nullable=True),
    )
    op.add_column("event_error_log", sa.Column("from_state", sa.String(32), nullable=True))
    op.add_column(
        "event_error_log",
        sa.Column("to_state", sa.String(32), server_default=sa.text("''"), nullable=True),
    )
    op.add_column(
        "event_error_log",
        sa.Column("error_code", sa.String(64), server_default=sa.text("''"), nullable=True),
    )
    op.add_column("event_error_log", sa.Column("error_msg", sa.String(512), nullable=True))
    op.add_column(
        "event_error_log",
        sa.Column(
            "payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=True,
        ),
    )
    op.add_column(
        "event_error_log",
        sa.Column("retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "event_error_log",
        sa.Column("max_retries", sa.Integer(), server_default=sa.text("5"), nullable=False),
    )
    op.add_column(
        "event_error_log", sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "event_error_log",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "event_error_log",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.execute(
        """
        UPDATE event_error_log
           SET platform        = COALESCE(platform,        ''),
               shop_id         = COALESCE(shop_id,         ''),
               order_no        = COALESCE(order_no,        ''),
               idempotency_key = COALESCE(idempotency_key, ''),
               to_state        = COALESCE(to_state,        ''),
               error_code      = COALESCE(error_code,      ''),
               payload_json    = COALESCE(payload_json,    '{}'::jsonb)
        """
    )

    for col in ("platform", "shop_id", "order_no", "idempotency_key", "to_state", "error_code"):
        op.alter_column(
            "event_error_log", col, existing_type=sa.String(), nullable=False, server_default=None
        )
    op.alter_column(
        "event_error_log",
        "payload_json",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=True,
        server_default=None,
    )

    if not _has_index("ix_event_error_log_key"):
        op.create_index(
            "ix_event_error_log_key",
            "event_error_log",
            ["platform", "shop_id", "idempotency_key"],
            unique=False,
        )
    if not _has_index("ix_event_error_log_retry"):
        op.create_index(
            "ix_event_error_log_retry",
            "event_error_log",
            ["next_retry_at"],
            unique=False,
        )

    # -----------------------------
    # inventory_movements：先建枚举 → 加列 → 回填 → 清洗 → 非空/索引/外键
    # -----------------------------
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'movementtype') THEN
                CREATE TYPE movementtype AS ENUM ('RECEIPT','SHIPMENT','TRANSFER','ADJUSTMENT');
            END IF;
        END $$;
        """
    )

    # 列添加前先守卫，避免 DuplicateColumn
    if not _has_column("inventory_movements", "item_sku"):
        op.add_column("inventory_movements", sa.Column("item_sku", sa.String(), nullable=True))
    if not _has_column("inventory_movements", "from_location_id"):
        op.add_column(
            "inventory_movements", sa.Column("from_location_id", sa.Integer(), nullable=True)
        )
    if not _has_column("inventory_movements", "to_location_id"):
        op.add_column(
            "inventory_movements", sa.Column("to_location_id", sa.Integer(), nullable=True)
        )
    if not _has_column("inventory_movements", "quantity"):
        op.add_column(
            "inventory_movements",
            sa.Column("quantity", sa.Float(), server_default=sa.text("0"), nullable=True),
        )
    if not _has_column("inventory_movements", "movement_type"):
        op.add_column(
            "inventory_movements",
            sa.Column(
                "movement_type",
                sa.Enum("RECEIPT", "SHIPMENT", "TRANSFER", "ADJUSTMENT", name="movementtype"),
                server_default=sa.text("'ADJUSTMENT'"),
                nullable=True,
            ),
        )
    if not _has_column("inventory_movements", "timestamp"):
        op.add_column(
            "inventory_movements",
            sa.Column(
                "timestamp",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )

    op.execute(
        """
        UPDATE inventory_movements
           SET quantity = COALESCE(quantity, 0),
               movement_type = COALESCE(movement_type, 'ADJUSTMENT')
        """
    )

    op.execute(
        """
        DELETE FROM inventory_movements im
        WHERE (from_location_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM locations l WHERE l.id = im.from_location_id))
           OR (to_location_id   IS NOT NULL AND NOT EXISTS (SELECT 1 FROM locations l WHERE l.id = im.to_location_id))
           OR (item_sku         IS NOT NULL AND NOT EXISTS (SELECT 1 FROM items     i WHERE i.sku = im.item_sku));
        """
    )

    op.alter_column(
        "inventory_movements",
        "quantity",
        existing_type=sa.Float(),
        nullable=False,
        server_default=None,
    )
    op.alter_column(
        "inventory_movements",
        "movement_type",
        existing_type=sa.Enum(name="movementtype"),
        nullable=False,
        server_default=None,
    )

    op.execute("ALTER TABLE inventory_movements ALTER COLUMN id TYPE text USING id::text")

    if not _has_index("ix_inventory_movements_id"):
        op.create_index(
            "ix_inventory_movements_id",
            "inventory_movements",
            ["id"],
            unique=False,
        )
    if not _has_index("ix_inventory_movements_item_sku"):
        op.create_index(
            "ix_inventory_movements_item_sku",
            "inventory_movements",
            ["item_sku"],
            unique=False,
        )
    if not _has_index("ix_inventory_movements_movement_type"):
        op.create_index(
            "ix_inventory_movements_movement_type",
            "inventory_movements",
            ["movement_type"],
            unique=False,
        )
    if not _has_index("ix_inventory_movements_sku_time"):
        op.create_index(
            "ix_inventory_movements_sku_time",
            "inventory_movements",
            ["item_sku", "timestamp"],
            unique=False,
        )
    if not _has_index("ix_inventory_movements_type_time"):
        op.create_index(
            "ix_inventory_movements_type_time",
            "inventory_movements",
            ["movement_type", "timestamp"],
            unique=False,
        )

    op.create_foreign_key(None, "inventory_movements", "locations", ["to_location_id"], ["id"])
    op.create_foreign_key(None, "inventory_movements", "locations", ["from_location_id"], ["id"])
    op.create_foreign_key(None, "inventory_movements", "items", ["item_sku"], ["sku"])

    # -----------------------------
    # 其它结构对齐（与 autogenerate 一致）
    # -----------------------------
    op.alter_column(
        "order_items",
        "id",
        existing_type=sa.INTEGER(),
        type_=sa.BigInteger(),
        existing_nullable=False,
        autoincrement=True,
    )
    op.alter_column(
        "order_items",
        "order_id",
        existing_type=sa.INTEGER(),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )
    op.alter_column("order_items", "item_id", existing_type=sa.INTEGER(), nullable=False)

    op.add_column("order_logistics", sa.Column("carrier", sa.String(length=64), nullable=True))
    op.add_column(
        "order_logistics",
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.alter_column(
        "order_logistics",
        "id",
        existing_type=sa.BIGINT(),
        type_=sa.Integer(),
        existing_nullable=False,
        autoincrement=True,
    )

    op.alter_column(
        "orders",
        "id",
        existing_type=sa.INTEGER(),
        type_=sa.BigInteger(),
        existing_nullable=False,
        autoincrement=True,
        existing_server_default=sa.text("nextval('orders_id_seq'::regclass)"),
    )

    op.add_column("platform_events", sa.Column("shop_id", sa.Text(), nullable=False))
    op.alter_column(
        "platform_events",
        "id",
        existing_type=sa.BIGINT(),
        type_=sa.Integer(),
        existing_nullable=False,
        autoincrement=True,
    )
    op.alter_column("platform_events", "dedup_key", existing_type=sa.TEXT(), nullable=True)

    if not _has_index("ix_reservation_lines_item"):
        op.create_index(
            "ix_reservation_lines_item",
            "reservation_lines",
            ["item_id"],
            unique=False,
        )
    if not _has_index("ix_reservation_lines_ref_line"):
        op.create_index(
            "ix_reservation_lines_ref_line",
            "reservation_lines",
            ["ref_line"],
            unique=False,
        )
    op.create_foreign_key(None, "reservation_lines", "reservations", ["reservation_id"], ["id"])

    # ---- 捕获并删除所有依赖 stock_ledger 的视图，再改列类型 ----
    captured_ledger_views = _capture_and_drop_views_depending_on("stock_ledger")

    _drop_index_or_constraint_if_exists("uq_ledger_reason_ref_refline_stock", "stock_ledger")

    op.alter_column(
        "stock_ledger",
        "reason",
        existing_type=sa.VARCHAR(length=32),
        type_=sa.String(length=64),
        existing_nullable=False,
        existing_server_default=sa.text("'ADJUST'::character varying"),
    )
    op.alter_column(
        "stock_ledger",
        "ref",
        existing_type=sa.VARCHAR(length=64),
        type_=sa.String(length=128),
        nullable=False,
    )
    op.create_index(
        "uq_ledger_reason_ref_refline_stock",
        "stock_ledger",
        ["reason", "ref", "ref_line", "stock_id"],
        unique=True,
    )

    _recreate_views(captured_ledger_views)

    # ---- 捕获并删除所有依赖 stocks 的视图，再改列类型 ----
    captured_stock_views = _capture_and_drop_views_depending_on("stocks")

    op.alter_column(
        "stocks", "batch_id", existing_type=sa.BIGINT(), type_=sa.Integer(), nullable=True
    )
    # 先清理潜在旧外键（若存在），再补建新外键（稳妥起见留幂等 drop 可选）
    # 这里直接建即可：上游已清洗脏数据
    op.create_foreign_key(None, "stocks", "items", ["item_id"], ["id"])
    op.create_foreign_key(None, "stocks", "locations", ["location_id"], ["id"])
    op.create_foreign_key(None, "stocks", "batches", ["batch_id"], ["id"])

    _recreate_views(captured_stock_views)


def downgrade() -> None:
    """Downgrade schema（mirror, best-effort）."""
    # stocks
    op.drop_constraint(None, "stocks", type_="foreignkey")
    op.drop_constraint(None, "stocks", type_="foreignkey")
    op.drop_constraint(None, "stocks", type_="foreignkey")
    op.alter_column(
        "stocks", "batch_id", existing_type=sa.Integer(), type_=sa.BIGINT(), nullable=False
    )

    # stock_ledger
    _drop_index_or_constraint_if_exists("uq_ledger_reason_ref_refline_stock", "stock_ledger")
    op.alter_column(
        "stock_ledger",
        "ref",
        existing_type=sa.String(length=128),
        type_=sa.VARCHAR(length=64),
        nullable=True,
    )
    op.alter_column(
        "stock_ledger",
        "reason",
        existing_type=sa.String(length=64),
        type_=sa.VARCHAR(length=32),
        existing_nullable=False,
        existing_server_default=sa.text("'ADJUST'::character varying"),
    )

    # reservation_lines
    op.drop_constraint(None, "reservation_lines", type_="foreignkey")
    op.drop_index("ix_reservation_lines_ref_line", table_name="reservation_lines")
    op.drop_index("ix_reservation_lines_item", table_name="reservation_lines")

    # platform_events
    op.alter_column("platform_events", "dedup_key", existing_type=sa.TEXT(), nullable=False)
    op.alter_column(
        "platform_events",
        "id",
        existing_type=sa.Integer(),
        type_=sa.BIGINT(),
        existing_nullable=False,
        autoincrement=True,
    )
    op.drop_column("platform_events", "shop_id")

    # orders / logistics / items
    op.alter_column(
        "orders",
        "id",
        existing_type=sa.BigInteger(),
        type_=sa.INTEGER(),
        existing_nullable=False,
        autoincrement=True,
        existing_server_default=sa.text("nextval('orders_id_seq'::regclass)"),
    )
    op.alter_column(
        "order_logistics",
        "id",
        existing_type=sa.Integer(),
        type_=sa.BIGINT(),
        existing_nullable=False,
        autoincrement=True,
    )
    op.drop_column("order_logistics", "created_at")
    op.drop_column("order_logistics", "carrier")

    op.alter_column("order_items", "item_id", existing_type=sa.INTEGER(), nullable=True)
    op.alter_column(
        "order_items",
        "order_id",
        existing_type=sa.BigInteger(),
        type_=sa.INTEGER(),
        existing_nullable=False,
    )
    op.alter_column(
        "order_items",
        "id",
        existing_type=sa.BigInteger(),
        type_=sa.INTEGER(),
        existing_nullable=False,
        autoincrement=True,
    )

    # inventory_movements
    op.drop_constraint(None, "inventory_movements", type_="foreignkey")
    op.drop_constraint(None, "inventory_movements", type_="foreignkey")
    op.drop_constraint(None, "inventory_movements", type_="foreignkey")
    op.drop_index("ix_inventory_movements_type_time", table_name="inventory_movements")
    op.drop_index("ix_inventory_movements_sku_time", table_name="inventory_movements")
    op.drop_index("ix_inventory_movements_movement_type", table_name="inventory_movements")
    op.drop_index("ix_inventory_movements_item_sku", table_name="inventory_movements")
    op.drop_index("ix_inventory_movements_id", table_name="inventory_movements")
    op.execute("ALTER TABLE inventory_movements ALTER COLUMN id TYPE integer USING id::integer")
    op.drop_column("inventory_movements", "timestamp")
    op.drop_column("inventory_movements", "movement_type")
    op.drop_column("inventory_movements", "quantity")
    op.drop_column("inventory_movements", "to_location_id")
    op.drop_column("inventory_movements", "from_location_id")
    op.drop_column("inventory_movements", "item_sku")

    # 删除枚举类型（若无依赖）
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'movementtype') THEN
                DROP TYPE movementtype;
            END IF;
        END $$;
        """
    )

    # event_error_log
    op.drop_index("ix_event_error_log_retry", table_name="event_error_log")
    op.drop_index("ix_event_error_log_key", table_name="event_error_log")
    for col in (
        "updated_at",
        "created_at",
        "next_retry_at",
        "max_retries",
        "retry_count",
        "payload_json",
        "error_msg",
        "error_code",
        "to_state",
        "from_state",
        "idempotency_key",
        "order_no",
        "shop_id",
        "platform",
    ):
        op.drop_column("event_error_log", col)
