"""ensure stock_ledger shape on PostgreSQL (idempotent, with backfill)

- Unify columns: stock_id, reason, after_qty, delta, occurred_at, ref, ref_line
- Best-effort backfill from legacy names
- Add NOT NULL where safe (deferred if blocking data exists)
- Add UNIQUE(reason, ref, ref_line) conditionally
- Add FK(stock_id) -> stocks(id)
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision = "20251014_ensure_stock_ledger_shape_on_pg"
down_revision = "31fc28eac057"  # <-- 如果与你项目不符，请改为当前 head
branch_labels = None
depends_on = None


TABLE = "stock_ledger"

REQ_COLS = {
    "stock_id": sa.Column("stock_id", sa.Integer, nullable=True),
    "reason": sa.Column("reason", sa.String(length=32), nullable=True),
    "after_qty": sa.Column("after_qty", sa.Numeric(18, 6), nullable=True),
    "delta": sa.Column("delta", sa.Numeric(18, 6), nullable=True),
    "occurred_at": sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
    "ref": sa.Column("ref", sa.String(length=64), nullable=True),
    "ref_line": sa.Column("ref_line", sa.String(length=32), nullable=True),
}

# 可能的历史别名（按优先级）
BACKFILL_SOURCES = {
    "after_qty": ["qty_after", "quantity_after", "after_quantity"],
    "delta": ["change_qty", "qty_change", "quantity_change", "change"],
    "occurred_at": ["created_at", "ts", "timestamp", "occurred"],  # pick tz-aware if exists
    "reason": ["type", "event", "action_reason"],
    "ref": ["reference", "doc_ref"],
    "ref_line": ["reference_line", "doc_line", "refline", "doc_ref_line"],
    "stock_id": ["stocks_id", "stock", "stock_fk"],
}

UQ_NAME = "uq_stock_ledger_reason_ref_refline"
FK_NAME = "fk_stock_ledger_stock_id_stocks"


def _has_table(bind, table: str) -> bool:
    res = bind.execute(
        text(
            """
        SELECT to_regclass(:t) IS NOT NULL;
    """
        ),
        {"t": table},
    ).scalar()
    return bool(res)


def _col_exists(bind, table: str, col: str) -> bool:
    sql = """
    SELECT 1
    FROM information_schema.columns
    WHERE table_name=:t AND column_name=:c
    LIMIT 1;
    """
    return bind.execute(text(sql), {"t": table, "c": col}).scalar() is not None


def _rename_col_if_exists(bind, table: str, old: str, new: str) -> bool:
    if _col_exists(bind, table, old) and not _col_exists(bind, table, new):
        op.alter_column(table, old, new_column_name=new)
        return True
    return False


def _try_add_column(bind, table: str, col_name: str, col: sa.Column):
    if not _col_exists(bind, table, col_name):
        op.add_column(table, col.copy())


def _first_existing_col(bind, table: str, candidates: list[str]) -> str | None:
    for c in candidates:
        if _col_exists(bind, table, c):
            return c
    return None


def _constraint_exists(bind, schema: str | None, name: str) -> bool:
    q = """
    SELECT 1
    FROM pg_constraint
    WHERE conname = :name
    LIMIT 1;
    """
    return bind.execute(text(q), {"name": name}).scalar() is not None


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, TABLE):
        # 如果老环境尚未创建该表，安全返回（由其他迁移负责创建）
        return

    # 1) 先尝试把历史列直接“重命名为目标名”（优先）
    for target, aliases in BACKFILL_SOURCES.items():
        for alias in aliases:
            if _rename_col_if_exists(bind, TABLE, alias, target):
                break  # 单个目标只改一次

    # 2) 确保目标列都存在（不存在则新增为可空）
    for name, col in REQ_COLS.items():
        _try_add_column(bind, TABLE, name, col)

    # 3) 回填：如果目标列存在为 NULL，而历史别名中还有其它可用列，则用它们回填一次
    #    注意：只在目标列存在且为 NULL 的行才回填
    for target, aliases in BACKFILL_SOURCES.items():
        if not _col_exists(bind, TABLE, target):
            continue
        source = _first_existing_col(bind, TABLE, aliases)
        if source:
            bind.execute(
                text(
                    f"""
                UPDATE {TABLE}
                SET {target} = {source}
                WHERE {target} IS NULL AND {source} IS NOT NULL;
            """
                )
            )

    # 4) 尝试设置 NOT NULL（条件性：只有在无 NULL 时收紧）
    def _set_not_null_if_clean(column: str):
        nulls = bind.execute(text(f"SELECT COUNT(*) FROM {TABLE} WHERE {column} IS NULL;")).scalar()
        if nulls == 0:
            op.alter_column(TABLE, column, existing_type=REQ_COLS[column].type, nullable=False)

    for must_have in ["stock_id", "reason", "after_qty", "delta", "occurred_at"]:
        _set_not_null_if_clean(must_have)

    # 5) 添加/修复外键 FK(stock_id) -> stocks(id)（如果不存在）
    if not _constraint_exists(bind, None, FK_NAME):
        try:
            op.create_foreign_key(
                FK_NAME,
                source_table=TABLE,
                referent_table="stocks",
                local_cols=["stock_id"],
                remote_cols=["id"],
                ondelete="RESTRICT",
                onupdate="CASCADE",
            )
        except Exception:
            # 若历史上存在匿名 FK，或数据不一致导致失败，跳过；交由校验脚本报告
            pass

    # 6) 添加唯一约束 UNIQUE(reason, ref, ref_line)，跳过 ref/ref_line 为 NULL 的情形由唯一约束自身允许
    #    这里统一添加普通 UNIQUE（PG 对多个 NULL 视为不同，不冲突）；若已存在则跳过
    if not _constraint_exists(bind, None, UQ_NAME):
        # 先检查是否存在冲突的重复数据（仅针对 not-null 三列）
        dup_cnt = bind.execute(
            text(
                f"""
            SELECT COUNT(*) FROM (
              SELECT reason, ref, ref_line, COUNT(*) cnt
              FROM {TABLE}
              WHERE reason IS NOT NULL AND ref IS NOT NULL AND ref_line IS NOT NULL
              GROUP BY reason, ref, ref_line
              HAVING COUNT(*) > 1
            ) t
        """
            )
        ).scalar()
        if dup_cnt == 0:
            try:
                op.create_unique_constraint(
                    UQ_NAME,
                    TABLE,
                    ["reason", "ref", "ref_line"],
                )
            except Exception:
                # 老环境可能已有同构 UQ 名称不同；跳过，交由校验脚本兜底
                pass


def downgrade() -> None:
    # 为安全起见，降级只移除我们明确创建且好辨识的约束，不回滚列改名/回填
    bind = op.get_bind()
    if _constraint_exists(bind, None, UQ_NAME):
        op.drop_constraint(UQ_NAME, TABLE, type_="unique")
    if _constraint_exists(bind, None, FK_NAME):
        op.drop_constraint(FK_NAME, TABLE, type_="foreignkey")
    # 不删除列，避免数据丢失
