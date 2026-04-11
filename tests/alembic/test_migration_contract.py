# tests/alembic/test_migration_contract.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


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


async def test_alembic_single_head_and_stocks_lot_contract(session: AsyncSession) -> None:
    # 1) single head
    r = await session.execute(text("SELECT COUNT(*) FROM alembic_version"))
    assert int(r.scalar_one() or 0) == 1

    # 2) stocks_lot.lot_id NOT NULL (schema-level contract)
    r2 = await session.execute(
        text(
            """
            SELECT is_nullable
              FROM information_schema.columns
             WHERE table_schema='public'
               AND table_name='stocks_lot'
               AND column_name='lot_id'
            """
        )
    )
    is_nullable = (r2.scalar_one_or_none() or "").strip().upper()
    assert is_nullable == "NO", "stocks_lot.lot_id must be NOT NULL in lot-world"

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
