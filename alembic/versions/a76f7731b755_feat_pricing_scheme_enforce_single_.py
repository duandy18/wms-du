"""feat(pricing-scheme): enforce single active scheme per provider

Revision ID: a76f7731b755
Revises: 2aff8011003f
Create Date: 2026-01-28 17:40:06.100197

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a76f7731b755"
down_revision: Union[str, Sequence[str], None] = "2aff8011003f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    ✅ 系统裁决：同一 shipping_provider_id 下，active=true 且 archived_at is null 只能存在一条。

    本迁移包含两步：
    1) datafix：清理历史“多活”脏数据（每个 provider 只保留一条 active）
    2) schema：创建 partial unique index 作为 DB 铁门
    """

    # 1) datafix：每个 provider（未归档）只保留 id 最大的一条 active=true，其余 active=false
    op.execute(
        sa.text(
            """
            WITH winners AS (
              SELECT shipping_provider_id, MAX(id) AS keep_id
              FROM shipping_provider_pricing_schemes
              WHERE archived_at IS NULL AND active IS TRUE
              GROUP BY shipping_provider_id
              HAVING COUNT(*) > 1
            )
            UPDATE shipping_provider_pricing_schemes s
            SET active = FALSE
            FROM winners w
            WHERE s.shipping_provider_id = w.shipping_provider_id
              AND s.archived_at IS NULL
              AND s.active IS TRUE
              AND s.id <> w.keep_id;
            """
        )
    )

    # 2) DB 铁门：同一 provider 的 active=true（且未归档）只能一条
    op.create_index(
        "uq_pricing_schemes_one_active_per_provider",
        "shipping_provider_pricing_schemes",
        ["shipping_provider_id"],
        unique=True,
        postgresql_where=sa.text("active IS TRUE AND archived_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_pricing_schemes_one_active_per_provider",
        table_name="shipping_provider_pricing_schemes",
    )
