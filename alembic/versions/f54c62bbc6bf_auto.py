"""auto

Revision ID: f54c62bbc6bf
Revises: 27681ae38581
Create Date: 2026-02-06 12:22:49.205858

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f54c62bbc6bf"
down_revision: Union[str, Sequence[str], None] = "27681ae38581"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _safe_add_unique_constraint(name: str, table: str, cols: list[str]) -> None:
    cols_sql = ", ".join(cols)
    op.execute(
        f"""
DO $$
BEGIN
    ALTER TABLE {table} ADD CONSTRAINT {name} UNIQUE ({cols_sql});
EXCEPTION
    WHEN duplicate_object OR duplicate_table THEN
        -- constraint (relation name) already exists
        NULL;
END $$;
""".strip()
    )


def _safe_create_index(name: str, table: str, cols: list[str], *, unique: bool = False) -> None:
    cols_sql = ", ".join(cols)
    uq = "UNIQUE " if unique else ""
    op.execute(f"CREATE {uq}INDEX IF NOT EXISTS {name} ON {table} ({cols_sql});")


def upgrade() -> None:
    """Upgrade schema."""
    # 1) print_jobs unique: (kind, ref_type, ref_id)
    _safe_add_unique_constraint("uq_print_jobs_pick_list_ref", "print_jobs", ["kind", "ref_type", "ref_id"])

    # 2) comment drift: return_task_lines.order_line_id
    op.alter_column(
        "return_task_lines",
        "order_line_id",
        existing_type=sa.BIGINT(),
        comment="可选：关联订单行 order_lines.id（用于更强边界/追溯）",
        existing_comment="可选：关联订单行 order_lines.id",
        existing_nullable=True,
    )

    # 3) indexes on shipping_provider_pricing_scheme_warehouses
    _safe_create_index(
        "ix_shipping_provider_pricing_scheme_warehouses_active",
        "shipping_provider_pricing_scheme_warehouses",
        ["active"],
    )
    _safe_create_index(
        "ix_shipping_provider_pricing_scheme_warehouses_scheme_id",
        "shipping_provider_pricing_scheme_warehouses",
        ["scheme_id"],
    )
    _safe_create_index(
        "ix_shipping_provider_pricing_scheme_warehouses_warehouse_id",
        "shipping_provider_pricing_scheme_warehouses",
        ["warehouse_id"],
    )

    # 4) shipping_providers.code nullable drift
    op.alter_column(
        "shipping_providers",
        "code",
        existing_type=sa.VARCHAR(length=64),
        nullable=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "shipping_providers",
        "code",
        existing_type=sa.VARCHAR(length=64),
        nullable=False,
    )

    op.drop_index(
        "ix_shipping_provider_pricing_scheme_warehouses_warehouse_id",
        table_name="shipping_provider_pricing_scheme_warehouses",
    )
    op.drop_index(
        "ix_shipping_provider_pricing_scheme_warehouses_scheme_id",
        table_name="shipping_provider_pricing_scheme_warehouses",
    )
    op.drop_index(
        "ix_shipping_provider_pricing_scheme_warehouses_active",
        table_name="shipping_provider_pricing_scheme_warehouses",
    )

    op.alter_column(
        "return_task_lines",
        "order_line_id",
        existing_type=sa.BIGINT(),
        comment="可选：关联订单行 order_lines.id",
        existing_comment="可选：关联订单行 order_lines.id（用于更强边界/追溯）",
        existing_nullable=True,
    )

    op.drop_constraint("uq_print_jobs_pick_list_ref", "print_jobs", type_="unique")
