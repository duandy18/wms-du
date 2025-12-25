"""add default_pricing_mode to shipping_provider_pricing_schemes

Revision ID: 25e65824f08a
Revises: 6859e0631616
Create Date: 2025-12-23 12:53:29.837366

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "25e65824f08a"
down_revision: Union[str, Sequence[str], None] = "6859e0631616"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_sqlite(bind) -> bool:
    return (bind.dialect.name or "").lower() == "sqlite"


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    sqlite = _is_sqlite(bind)

    insp = sa.inspect(bind)
    schema = None if sqlite else "public"

    # 表不存在就不做（避免裁剪 scope / 测试环境误炸）
    if "shipping_provider_pricing_schemes" not in insp.get_table_names(schema=schema):
        return

    cols = [c["name"] for c in insp.get_columns("shipping_provider_pricing_schemes", schema=schema)]

    # 1) 增加列（若已存在则跳过）
    if "default_pricing_mode" not in cols:
        op.add_column(
            "shipping_provider_pricing_schemes",
            sa.Column(
                "default_pricing_mode",
                sa.String(32),
                nullable=False,
                server_default=sa.text("'linear_total'"),
            ),
        )

    # 2) Postgres：加 CHECK 约束（SQLite 跳过）
    if not sqlite:
        op.execute(
            """
            ALTER TABLE shipping_provider_pricing_schemes
            ADD CONSTRAINT ck_shipping_provider_pricing_schemes_default_pricing_mode
            CHECK (default_pricing_mode in ('flat','linear_total','step_over','manual_quote'))
            """
        )

        # 3) 确保默认值 & NOT NULL（防止历史库里列被手工加过但没 default）
        op.execute(
            """
            ALTER TABLE shipping_provider_pricing_schemes
            ALTER COLUMN default_pricing_mode SET DEFAULT 'linear_total'
            """
        )
        op.execute(
            """
            UPDATE shipping_provider_pricing_schemes
               SET default_pricing_mode = 'linear_total'
             WHERE default_pricing_mode IS NULL OR default_pricing_mode = ''
            """
        )
        op.execute(
            """
            ALTER TABLE shipping_provider_pricing_schemes
            ALTER COLUMN default_pricing_mode SET NOT NULL
            """
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    sqlite = _is_sqlite(bind)

    insp = sa.inspect(bind)
    schema = None if sqlite else "public"

    if "shipping_provider_pricing_schemes" not in insp.get_table_names(schema=schema):
        return

    cols = [c["name"] for c in insp.get_columns("shipping_provider_pricing_schemes", schema=schema)]
    if "default_pricing_mode" not in cols:
        return

    if not sqlite:
        op.execute(
            """
            ALTER TABLE shipping_provider_pricing_schemes
            DROP CONSTRAINT IF EXISTS ck_shipping_provider_pricing_schemes_default_pricing_mode
            """
        )

    op.drop_column("shipping_provider_pricing_schemes", "default_pricing_mode")
