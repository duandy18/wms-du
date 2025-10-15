"""Ensure stock_ledger shape on PostgreSQL (idempotent + backfill)

- Target columns:
    stock_id (int), reason (str32), after_qty (numeric(18,6)),
    delta (numeric(18,6)), occurred_at (timestamptz), ref (str64), ref_line (str32)
- Steps:
    * rename legacy columns when possible
    * add missing columns (nullable)
    * backfill from legacy aliases
    * tighten NOT NULL where data allows (no NULLs)
    * add FK(stock_id)->stocks(id) if safe
    * add UNIQUE(reason,ref,ref_line) if no duplicates
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision = "3b1f9c2e1a5b"
down_revision = "40a7b8b5e6d1"
branch_labels = None
depends_on = None

TABLE = "stock_ledger"

REQ_COLS = {
    "stock_id": sa.Integer,
    "reason": sa.String(length=32),
    "after_qty": sa.Numeric(18, 6),
    "delta": sa.Numeric(18, 6),
    "occurred_at": sa.DateTime(timezone=True),
    "ref": sa.String(length=64),
    "ref_line": sa.String(length=32),
}

# 历史别名（按优先级）
ALIASES = {
    "after_qty": ["qty_after", "quantity_after", "after_quantity"],
    "delta": ["change_qty", "qty_change", "quantity_change", "change"],
    "occurred_at": ["created_at", "ts", "timestamp", "occurred"],
    "reason": ["type", "event", "action_reason"],
    "ref": ["reference", "doc_ref"],
    "ref_line": ["reference_line", "doc_line", "refline", "doc_ref_line"],
    "stock_id": ["stocks_id", "stock", "stock_fk"],
}

UQ_NAME = "uq_stock_ledger_reason_ref_refline"
FK_NAME = "fk_stock_ledger_stock_id_stocks"


# ---------- helpers (纯 SQL，避免依赖未注入的对象) ----------
def _has_table(bind, table: str) -> bool:
    return bool(bind.execute(text("SELECT to_regclass(:t) IS NOT NULL"), {"t": table}).scalar())


def _col_exists(bind, table: str, col: str) -> bool:
    sql = """
    SELECT 1
    FROM information_schema.columns
    WHERE table_name = :t AND column_name = :c
    LIMIT 1;
    """
    return bind.execute(text(sql), {"t": table, "c": col}).scalar() is not None


def _constraint_exists(bind, name: str) -> bool:
    sql = "SELECT 1 FROM pg_constraint WHERE conname = :n LIMIT 1"
    return bind.execute(text(sql), {"n": name}).scalar() is not None


def _rename_col_if_exists(bind, table: str, old: str, new: str) -> bool:
    if _col_exists(bind, table, old) and not _col_exists(bind, table, new):
        op.alter_column(table, old, new_column_name=new)
        return True
    return False


def _add_col_if_missing(table: str, col: str, type_: sa.types.TypeEngine):
    if not _col_exists(op.get_bind(), table, col):
        op.add_column(table, sa.Column(col, type_, nullable=True))


def _first_existing_alias(bind, table: str, candidates: list[str]) -> str | None:
    for c in candidates:
        if _col_exists(bind, table, c):
            return c
    return None


# ---------- migration ----------
def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, TABLE):
        # 老环境可能还没创建该表；此迁移只做“收敛”，若无表则跳过
        return

    # 1) 优先做“重命名为目标名”（避免重复 add + backfill）
    for target, alist in ALIASES.items():
        for alias in alist:
            if _rename_col_if_exists(bind, TABLE, alias, target):
                break

    # 2) 确保目标列都存在（若缺失则新增为可空）
    for name, typ in REQ_COLS.items():
        _add_col_if_missing(TABLE, name, typ)

    # 3) backfill：若目标列仍有 NULL，且还存在某个 alias 列，则用它补齐
    for target, alist in ALIASES.items():
        if not _col_exists(bind, TABLE, target):
            continue
        src = _first_existing_alias(bind, TABLE, alist)
        if src:
            bind.execute(
                text(
                    f"""
                    UPDATE {TABLE}
                    SET {target} = {src}
                    WHERE {target} IS NULL AND {src} IS NOT NULL
                    """
                )
            )

    # 4) 条件性收紧 NOT NULL（只有在该列无 NULL 时才收紧）
    def tighten_not_null(col: str):
        nulls = bind.execute(text(f"SELECT COUNT(*) FROM {TABLE} WHERE {col} IS NULL")).scalar()
        if nulls == 0:
            op.alter_column(TABLE, col, existing_type=REQ_COLS[col], nullable=False)

    for must in ["stock_id", "reason", "after_qty", "delta", "occurred_at"]:
        tighten_not_null(must)

    # 5) FK: stock_id -> stocks(id)（如果不存在）
    if not _constraint_exists(bind, FK_NAME):
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
            # 可能已有匿名 FK 或数据脏；跳过，交由校验脚本兜底
            pass

    # 6) UQ: (reason,ref,ref_line)（如果没有重复再建约束）
    if not _constraint_exists(bind, UQ_NAME):
        dup = bind.execute(
            text(
                f"""
                SELECT COUNT(*) FROM (
                  SELECT reason, ref, ref_line, COUNT(*) c
                  FROM {TABLE}
                  WHERE reason IS NOT NULL AND ref IS NOT NULL AND ref_line IS NOT NULL
                  GROUP BY reason, ref, ref_line
                  HAVING COUNT(*) > 1
                ) t
                """
            )
        ).scalar()
        if dup == 0:
            try:
                op.create_unique_constraint(UQ_NAME, TABLE, ["reason", "ref", "ref_line"])
            except Exception:
                # 可能存在同构不同名约束；跳过
                pass


def downgrade() -> None:
    # 仅撤销我们能明确识别的约束；不删除列，避免数据丢失
    bind = op.get_bind()
    if _constraint_exists(bind, UQ_NAME):
        op.drop_constraint(UQ_NAME, TABLE, type_="unique")
    if _constraint_exists(bind, FK_NAME):
        op.drop_constraint(FK_NAME, TABLE, type_="foreignkey")
