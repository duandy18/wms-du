# tests/alembic/test_migration_contract.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


LOT_WORLD_TABLES = (
    "stock_ledger",
    "stocks_lot",
    "stock_snapshots",
)

FORBIDDEN_BATCH_WORLD_COLUMNS = {
    "batch_code",
    "batch_code_key",
    "lot_id_key",
}


async def _get_index_defs(session: AsyncSession, *, table: str) -> list[str]:
    rows = await session.execute(
        text(
            """
            SELECT indexdef
              FROM pg_indexes
             WHERE schemaname='public'
               AND tablename=:t
             ORDER BY indexname
            """
        ),
        {"t": str(table)},
    )
    return [str(r[0]) for r in rows.fetchall()]


async def _get_table_columns(session: AsyncSession, *, table: str) -> set[str]:
    rows = await session.execute(
        text(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema='public'
               AND table_name=:t
             ORDER BY ordinal_position
            """
        ),
        {"t": str(table)},
    )
    return {str(r[0]) for r in rows.fetchall()}


async def _get_column_nullable(
    session: AsyncSession,
    *,
    table: str,
    column: str,
) -> str | None:
    row = await session.execute(
        text(
            """
            SELECT is_nullable
              FROM information_schema.columns
             WHERE table_schema='public'
               AND table_name=:t
               AND column_name=:c
            """
        ),
        {"t": str(table), "c": str(column)},
    )
    value = row.scalar_one_or_none()
    if value is None:
        return None
    return str(value).strip().upper()


def _has_required_unique_by_production_date(idx_defs: list[str]) -> bool:
    """
    Expect:
      UNIQUE (warehouse_id, item_id, production_date)
      WHERE lot_code_source='SUPPLIER'
        AND item_expiry_policy_snapshot='REQUIRED'
        AND production_date IS NOT NULL
    """
    for d in idx_defs:
        dd = d.lower()
        if "unique index" not in dd:
            continue
        if " on public.lots " not in dd:
            continue
        if "(warehouse_id, item_id, production_date)" not in dd:
            continue
        if "item_expiry_policy_snapshot" not in dd or "required" not in dd:
            continue
        if "production_date is not null" not in dd:
            continue
        if "lot_code_source" not in dd or "supplier" not in dd:
            continue
        return True
    return False


def _has_internal_singleton_unique(idx_defs: list[str]) -> bool:
    """
    Expect:
      UNIQUE (warehouse_id, item_id) WHERE lot_code_source='INTERNAL' AND lot_code IS NULL
    """
    for d in idx_defs:
        dd = d.lower()
        if "unique index" not in dd:
            continue
        if " on public.lots " not in dd:
            continue
        if "(warehouse_id, item_id)" in dd and "where" in dd and "lot_code is null" in dd and "internal" in dd:
            return True
    return False


def _has_legacy_unique_by_key(idx_defs: list[str]) -> bool:
    """
    Legacy (should be retired):
      UNIQUE (warehouse_id, item_id, lot_code_key) WHERE lot_code IS NOT NULL
    """
    for d in idx_defs:
        dd = d.lower()
        if "unique index" not in dd:
            continue
        if " on public.lots " not in dd:
            continue
        if "(warehouse_id, item_id, lot_code_key)" in dd and "where (lot_code is not null)" in dd:
            return True
    return False


async def test_alembic_single_head_and_lot_world_schema_contract(session: AsyncSession) -> None:
    # 1) single head
    r = await session.execute(text("SELECT COUNT(*) FROM alembic_version"))
    assert int(r.scalar_one() or 0) == 1

    # 2) lot-world structure tables must keep lot_id as the required structural anchor.
    for table in LOT_WORLD_TABLES:
        columns = await _get_table_columns(session, table=table)

        assert "lot_id" in columns, f"{table}.lot_id must exist in lot-world"

        nullable = await _get_column_nullable(session, table=table, column="lot_id")
        assert nullable == "NO", f"{table}.lot_id must be NOT NULL in lot-world"

        forbidden = FORBIDDEN_BATCH_WORLD_COLUMNS & columns
        assert not forbidden, f"{table} must not contain retired batch-world columns: {sorted(forbidden)}"

    # 3) lots indexes contracts
    idx_defs = await _get_index_defs(session, table="lots")
    assert _has_required_unique_by_production_date(idx_defs), (
        "missing required-lot uniqueness: "
        "UNIQUE (warehouse_id,item_id,production_date) "
        "WHERE lot_code_source='SUPPLIER' AND item_expiry_policy_snapshot='REQUIRED' AND production_date IS NOT NULL"
    )
    assert _has_internal_singleton_unique(idx_defs), (
        "missing internal-lot uniqueness: UNIQUE (warehouse_id,item_id) "
        "WHERE lot_code_source='INTERNAL' AND lot_code IS NULL"
    )
    assert not _has_legacy_unique_by_key(idx_defs), (
        "legacy supplier-lot uniqueness by lot_code_key must be retired"
    )
