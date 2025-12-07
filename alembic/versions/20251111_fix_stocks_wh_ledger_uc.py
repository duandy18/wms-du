"""收束迁移：仓库总账制 + 统一幂等 + 批次纯身份 + 三池视图

- stocks 唯一键 → (item_id, warehouse_id, batch_code)
- stock_ledger 幂等唯一 → (reason, ref, ref_line, item_id, batch_code, warehouse_id)
- batches 仅保留 (item_id, batch_code) 唯一，去位置耦合
- 种子三池：MAIN / RETURNS / QUARANTINE
- 视图：v_available（MAIN）、v_onhand（合计）、v_returns_pool（RETURNS）
"""

from alembic import op
import sqlalchemy as sa

# 版本标识
revision = "20251111_fix_stocks_wh_ledger_uc"
down_revision = "3f_fix_locations_id_default_seq_binding"
branch_labels = None
depends_on = None


# --------- 小工具 ---------
def _col_exists(conn, table, column) -> bool:
    return bool(
        conn.execute(
            sa.text("""
                SELECT 1
                FROM information_schema.columns
                WHERE table_name=:t AND column_name=:c
                LIMIT 1
            """),
            {"t": table, "c": column},
        ).fetchone()
    )

def _constraint_exists(conn, table, name) -> bool:
    return bool(
        conn.execute(
            sa.text("""
                SELECT 1
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid=con.conrelid
                WHERE rel.relname=:t AND con.conname=:n
                LIMIT 1
            """),
            {"t": table, "n": name},
        ).fetchone()
    )

def _index_exists(conn, name) -> bool:
    return bool(
        conn.execute(sa.text("SELECT 1 FROM pg_indexes WHERE indexname=:n LIMIT 1"),
                     {"n": name}).fetchone()
    )

def _drop_trigger_if_exists(conn, trg, table):
    conn.execute(sa.text(f'DROP TRIGGER IF EXISTS {trg} ON {table};'))

def _drop_function_if_exists(conn, funcsig):
    conn.execute(sa.text(f'DROP FUNCTION IF EXISTS {funcsig};'))

def _drop_view_if_exists(conn, vname, cascade=False):
    conn.execute(sa.text(f"DROP VIEW IF EXISTS {vname} {'CASCADE' if cascade else ''};"))

# 强制参数类型，避免 text/varchar 歧义
def _ensure_warehouse(conn, code: str) -> int:
    conn.execute(
        sa.text("""
            INSERT INTO warehouses(name)
            SELECT CAST(:n AS varchar)
            WHERE NOT EXISTS (
              SELECT 1 FROM warehouses WHERE name = CAST(:n AS varchar)
            )
        """),
        {"n": code},
    )
    wid = conn.execute(
        sa.text("SELECT id FROM warehouses WHERE name = CAST(:n AS varchar) LIMIT 1"),
        {"n": code},
    ).scalar()
    return int(wid)


# --------- 升级主流程 ---------
def upgrade():
    conn = op.get_bind()

    # 0) 预清理：老视图/触发器/函数（阻塞列/唯一键调整）
    for v in (
        "v_fefo_rank",
        "v_putaway_ledger_recent",
        "v_putaway_ledger_recent_explicit",
        "v_stocks_enriched",
    ):
        _drop_view_if_exists(conn, v, cascade=True)

    _drop_trigger_if_exists(conn, "trg_enforce_single_item_batch_per_location", "stocks")
    _drop_trigger_if_exists(conn, "trg_auto_unbind_location_when_empty", "stocks")
    for fn in ("enforce_single_item_batch_per_location()", "auto_unbind_location_when_empty()"):
        _drop_function_if_exists(conn, fn)

    for trg in (
        "fill_dims", "fill_item_id", "stock_ledger_fill_item_id",
        "trg_ledger_fill_item_id", "trg_stock_ledger_bi_fill_item",
        "trg_stock_ledger_dims", "trg_stock_ledger_fill_dims",
        "trg_stock_ledger_fill_item_id",
    ):
        _drop_trigger_if_exists(conn, trg, "stock_ledger")
    for fn in (
        "fill_dims()", "fill_item_id()", "stock_ledger_fill_dims()",
        "ledger_fill_item_id()", "stock_ledger_bi_fill_item()", "stock_ledger_fill_item_id()",
    ):
        _drop_function_if_exists(conn, fn)

    # 1) 三池
    wid_main = _ensure_warehouse(conn, "MAIN")
    _ensure_warehouse(conn, "RETURNS")
    _ensure_warehouse(conn, "QUARANTINE")

    # 2) batches：身份唯一 (item_id, batch_code)，去位置耦合
    for col in ("warehouse_id", "location_id"):
        if _col_exists(conn, "batches", col):
            op.drop_column("batches", col)

    for cname in ("uq_batches_unique", "uq_batches_item_loc_code", "uq_batches_item_wh_code", "uq_batches_composite"):
        if _constraint_exists(conn, "batches", cname):
            op.drop_constraint(cname, "batches", type_="unique")

    if not _constraint_exists(conn, "batches", "uq_batches_item_code"):
        op.create_unique_constraint("uq_batches_item_code", "batches", ["item_id", "batch_code"])

    if not _index_exists(conn, "ix_batches_item_code"):
        op.create_index("ix_batches_item_code", "batches", ["item_id", "batch_code"])

    for iname in ("ix_batches_location_id", "ix_batches_warehouse_id", "ix_batches_item_loc", "ix_batches_item_wh"):
        if _index_exists(conn, iname):
            op.drop_index(iname, table_name="batches")

    # 3) stocks：先全程禁用触发器 → 再做列与数据/约束调整 → 最后启用触发器
    conn.execute(sa.text("ALTER TABLE stocks DISABLE TRIGGER ALL"))

    # 3.1 warehouse_id
    if not _col_exists(conn, "stocks", "warehouse_id"):
        op.add_column("stocks", sa.Column("warehouse_id", sa.Integer(), nullable=True))
        conn.execute(sa.text("UPDATE stocks SET warehouse_id=:wid WHERE warehouse_id IS NULL"),
                     {"wid": wid_main})

    # 3.2 batch_code（从旧的 batch_id 关联 batches 回填）
    if not _col_exists(conn, "stocks", "batch_code"):
        op.add_column("stocks", sa.Column("batch_code", sa.String(length=64), nullable=True))
        if _col_exists(conn, "stocks", "batch_id"):
            conn.execute(sa.text("""
                UPDATE stocks s
                SET batch_code = b.batch_code
                FROM batches b
                WHERE s.batch_id IS NOT NULL AND b.id = s.batch_id AND s.batch_code IS NULL
            """))
        conn.execute(sa.text("UPDATE stocks SET batch_code = COALESCE(batch_code, '__NO_BATCH__')"))

    # 3.3 qty_on_hand（与旧 qty 对齐）
    if _col_exists(conn, "stocks", "qty_on_hand"):
        pass
    elif _col_exists(conn, "stocks", "qty"):
        conn.execute(sa.text("ALTER TABLE stocks RENAME COLUMN qty TO qty_on_hand"))
    else:
        op.add_column("stocks", sa.Column("qty_on_hand", sa.Integer(), nullable=False, server_default="0"))

    # 3.4 清理旧唯一（location 维度）
    for cname in (
        "uq_stocks_item_loc_batch",
        "uq_stocks_item_location_batch",
        "uq_stocks_item_location_id_batch_code",
        "uq_stocks_unique_item_loc_batch",
    ):
        if _constraint_exists(conn, "stocks", cname):
            op.drop_constraint(cname, "stocks", type_="unique")

    # 3.5 新唯一 + 索引
    if not _constraint_exists(conn, "stocks", "uq_stocks_item_wh_batch"):
        op.create_unique_constraint("uq_stocks_item_wh_batch", "stocks",
                                    ["item_id", "warehouse_id", "batch_code"])
    if not _index_exists(conn, "ix_stocks_item_wh_batch"):
        op.create_index("ix_stocks_item_wh_batch", "stocks", ["item_id", "warehouse_id", "batch_code"])

    # 3.6 设 NOT NULL / 清默认
    conn.execute(sa.text("ALTER TABLE stocks ALTER COLUMN warehouse_id SET NOT NULL"))
    conn.execute(sa.text("ALTER TABLE stocks ALTER COLUMN batch_code SET NOT NULL"))
    conn.execute(sa.text("ALTER TABLE stocks ALTER COLUMN qty_on_hand DROP DEFAULT"))

    # 3.7 重新启用触发器
    conn.execute(sa.text("ALTER TABLE stocks ENABLE TRIGGER ALL"))

    # 4) stock_ledger：补齐 warehouse_id / batch_code；统一幂等唯一
    if not _col_exists(conn, "stock_ledger", "warehouse_id"):
        op.add_column("stock_ledger", sa.Column("warehouse_id", sa.Integer(), nullable=True))
        try:
            conn.execute(sa.text("""
                UPDATE stock_ledger l
                SET warehouse_id = s.warehouse_id
                FROM stocks s
                WHERE l.stock_id IS NOT NULL AND s.id = l.stock_id AND l.warehouse_id IS NULL
            """))
        except Exception:
            pass
        conn.execute(sa.text("UPDATE stock_ledger SET warehouse_id=:wid WHERE warehouse_id IS NULL"),
                     {"wid": wid_main})

    if not _col_exists(conn, "stock_ledger", "batch_code"):
        op.add_column("stock_ledger", sa.Column("batch_code", sa.String(length=64), nullable=True))
        try:
            conn.execute(sa.text("""
                UPDATE stock_ledger l
                SET batch_code = s.batch_code
                FROM stocks s
                WHERE l.stock_id IS NOT NULL AND s.id = l.stock_id AND l.batch_code IS NULL
            """))
        except Exception:
            pass
        conn.execute(sa.text("UPDATE stock_ledger SET batch_code = COALESCE(batch_code, '__UNKNOWN__')"))

    for cname in ("uq_ledger_reason_ref_refline_stock",
                  "uq_ledger_reason_ref_line_item_batch",
                  "uq_ledger_reason_ref_line_item_batch_loc",
                  "uq_ledger_unique"):
        if _constraint_exists(conn, "stock_ledger", cname):
            op.drop_constraint(cname, "stock_ledger", type_="unique")

    if not _constraint_exists(conn, "stock_ledger", "uq_ledger_idem_reason_refline_item_code_wh"):
        op.create_unique_constraint("uq_ledger_idem_reason_refline_item_code_wh",
                                    "stock_ledger",
                                    ["reason", "ref", "ref_line", "item_id", "batch_code", "warehouse_id"])
    if not _index_exists(conn, "ix_ledger_dims"):
        op.create_index("ix_ledger_dims", "stock_ledger", ["item_id", "batch_code", "warehouse_id"])
    if not _index_exists(conn, "ix_ledger_occurred_at"):
        op.create_index("ix_ledger_occurred_at", "stock_ledger", ["occurred_at"])

    conn.execute(sa.text("ALTER TABLE stock_ledger ALTER COLUMN warehouse_id SET NOT NULL"))
    conn.execute(sa.text("ALTER TABLE stock_ledger ALTER COLUMN batch_code SET NOT NULL"))

    # 5) 三视图（新口径）
    for v in ("v_available", "v_onhand", "v_returns_pool"):
        _drop_view_if_exists(conn, v, cascade=True)

    conn.execute(sa.text("""
        CREATE VIEW v_available AS
        SELECT s.item_id, s.batch_code, s.warehouse_id, s.qty_on_hand AS qty
        FROM stocks s
        JOIN warehouses w ON w.id = s.warehouse_id
        WHERE w.name = 'MAIN';
    """))

    conn.execute(sa.text("""
        CREATE VIEW v_onhand AS
        SELECT s.item_id, s.batch_code, SUM(s.qty_on_hand) AS qty
        FROM stocks s
        GROUP BY s.item_id, s.batch_code;
    """))

    conn.execute(sa.text("""
        CREATE VIEW v_returns_pool AS
        SELECT s.item_id, s.batch_code, s.qty_on_hand
        FROM stocks s
        JOIN warehouses w ON w.id = s.warehouse_id
        WHERE w.name = 'RETURNS';
    """))


def downgrade():
    conn = op.get_bind()

    for v in ("v_available", "v_onhand", "v_returns_pool"):
        _drop_view_if_exists(conn, v, cascade=True)

    if _constraint_exists(conn, "stock_ledger", "uq_ledger_idem_reason_refline_item_code_wh"):
        op.drop_constraint("uq_ledger_idem_reason_refline_item_code_wh", "stock_ledger", type_="unique")
    for iname in ("ix_ledger_dims", "ix_ledger_occurred_at"):
        if _index_exists(conn, iname):
            op.drop_index(iname, table_name="stock_ledger")

    if _constraint_exists(conn, "stocks", "uq_stocks_item_wh_batch"):
        op.drop_constraint("uq_stocks_item_wh_batch", "stocks", type_="unique")
    if _index_exists(conn, "ix_stocks_item_wh_batch"):
        op.drop_index("ix_stocks_item_wh_batch", table_name="stocks")

    if _constraint_exists(conn, "batches", "uq_batches_item_code"):
        op.drop_constraint("uq_batches_item_code", "batches", type_="unique")
    if _index_exists(conn, "ix_batches_item_code"):
        op.drop_index("ix_batches_item_code", table_name="batches")
