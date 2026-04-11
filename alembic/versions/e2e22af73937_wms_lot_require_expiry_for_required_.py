"""wms_lot_require_expiry_for_required_supplier_lot

Revision ID: e2e22af73937
Revises: 3bd2a92976ba
Create Date: 2026-04-11 21:58:55.883692

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e2e22af73937"
down_revision: Union[str, Sequence[str], None] = "3bd2a92976ba"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CONSTRAINT_NAME = "ck_lots_required_supplier_expiry_not_null"
TABLE_NAME = "lots"


def _get_existing_check_def(conn) -> str | None:
    row = conn.execute(
        sa.text(
            """
            SELECT pg_get_constraintdef(c.oid) AS definition
              FROM pg_constraint c
              JOIN pg_class t
                ON t.oid = c.conrelid
             WHERE c.conname = :constraint_name
               AND c.contype = 'c'
               AND t.relname = :table_name
             ORDER BY c.oid
             LIMIT 1
            """
        ),
        {
            "constraint_name": CONSTRAINT_NAME,
            "table_name": TABLE_NAME,
        },
    ).mappings().first()
    if row is None:
        return None
    got = row["definition"]
    return str(got) if got is not None else None


def _normalize_sql(sql: str) -> str:
    return " ".join(str(sql or "").replace("\n", " ").split()).strip().upper()


def _constraint_def_looks_expected(definition: str) -> bool:
    norm = _normalize_sql(definition)
    required_fragments = (
        "CHECK",
        "ITEM_EXPIRY_POLICY_SNAPSHOT",
        "LOT_CODE_SOURCE",
        "EXPIRY_DATE IS NOT NULL",
        "'REQUIRED'",
        "'SUPPLIER'",
    )
    return all(fragment in norm for fragment in required_fragments)


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()

    # 先做一次保守回填：
    # 仅当同一 lot_id 在 stock_ledger 中存在唯一非空 expiry_date 时，
    # 才允许把 lots.expiry_date 从 NULL 补成该值。
    # 只补空，不覆盖已有非空值。
    conn.execute(
        sa.text(
            """
            WITH ledger_unique_expiry AS (
                SELECT
                    sl.lot_id AS lot_id,
                    MIN(sl.expiry_date) AS expiry_date
                FROM stock_ledger sl
                WHERE sl.lot_id IS NOT NULL
                  AND sl.expiry_date IS NOT NULL
                GROUP BY sl.lot_id
                HAVING COUNT(DISTINCT sl.expiry_date) = 1
            )
            UPDATE lots l
               SET expiry_date = src.expiry_date
              FROM ledger_unique_expiry src
             WHERE l.id = src.lot_id
               AND l.item_expiry_policy_snapshot = 'REQUIRED'
               AND l.lot_code_source = 'SUPPLIER'
               AND l.expiry_date IS NULL
            """
        )
    )

    null_count = conn.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM lots
            WHERE item_expiry_policy_snapshot = 'REQUIRED'
              AND lot_code_source = 'SUPPLIER'
              AND expiry_date IS NULL
            """
        )
    ).scalar_one()

    if int(null_count or 0) > 0:
        raise RuntimeError(
            "wms_lot_require_expiry_for_required_supplier_lot: "
            f"found {int(null_count)} REQUIRED+SUPPLIER lots with NULL expiry_date"
        )

    existing_def = _get_existing_check_def(conn)
    if existing_def is None:
        op.create_check_constraint(
            CONSTRAINT_NAME,
            TABLE_NAME,
            sa.text(
                "("
                "item_expiry_policy_snapshot <> 'REQUIRED' "
                "OR lot_code_source <> 'SUPPLIER' "
                "OR expiry_date IS NOT NULL"
                ")"
            ),
        )
        return

    if not _constraint_def_looks_expected(existing_def):
        raise RuntimeError(
            f"{CONSTRAINT_NAME}: constraint already exists on {TABLE_NAME}, "
            f"but definition is unexpected: {existing_def}"
        )


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()

    existing_def = _get_existing_check_def(conn)
    if existing_def is None:
        return

    if not _constraint_def_looks_expected(existing_def):
        raise RuntimeError(
            f"{CONSTRAINT_NAME}: constraint already exists on {TABLE_NAME}, "
            f"but definition is unexpected: {existing_def}"
        )

    op.drop_constraint(
        CONSTRAINT_NAME,
        TABLE_NAME,
        type_="check",
    )
