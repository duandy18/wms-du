"""ship_records_hard_idempotency

Revision ID: 21a347e34ad3
Revises: 23c23873be24
Create Date: 2026-03-04 15:45:53.861640

目标（Phase: shipping_records 事实收口）：
- shipping_records 以 (platform, shop_id, order_ref) 做硬幂等
- 回填 shipping_provider_id（由 carrier_code -> shipping_providers.code 映射）
- 补齐 FAKE provider（用于历史/演示数据 carrier_code='FAKE'）
- warehouse_id 补 FK，并收口为 NOT NULL
- shipping_provider_id 收口为 NOT NULL
- 可选但强烈建议：tracking_no 非空时在 (carrier_code, tracking_no) 维度唯一

注意：
- upgrade 会先去重，否则 unique 会失败
- downgrade 不会删除 FAKE provider（避免潜在引用风险）
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "21a347e34ad3"
down_revision: Union[str, Sequence[str], None] = "23c23873be24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) 去重：以 (platform, shop_id, order_ref) 为粒度保留最小 id
    op.execute(
        sa.text(
            """
            WITH ranked AS (
              SELECT
                id,
                ROW_NUMBER() OVER (
                  PARTITION BY platform, shop_id, order_ref
                  ORDER BY id ASC
                ) AS rn
              FROM shipping_records
            )
            DELETE FROM shipping_records sr
            USING ranked r
            WHERE sr.id = r.id
              AND r.rn > 1;
            """
        )
    )

    # 2) 补齐 FAKE provider（用于 carrier_code='FAKE' 的历史/演示数据回填）
    # code 在你们体系里是“不可变业务键”，这里只做 “不存在则插入”。
    op.execute(
        sa.text(
            """
            INSERT INTO shipping_providers (name, code, active, priority, external_outlet_code, address)
            SELECT 'Fake Express', 'FAKE', true, 100, 'FAKE-OUTLET', NULL
            WHERE NOT EXISTS (SELECT 1 FROM shipping_providers WHERE code = 'FAKE');
            """
        )
    )

    # 3) 回填 shipping_provider_id：carrier_code -> shipping_providers.code
    op.execute(
        sa.text(
            """
            UPDATE shipping_records sr
            SET shipping_provider_id = sp.id
            FROM shipping_providers sp
            WHERE sr.shipping_provider_id IS NULL
              AND sr.carrier_code IS NOT NULL
              AND sp.code = sr.carrier_code;
            """
        )
    )

    # 4) warehouse_id 收口：NOT NULL + FK
    # 数据取证已证明现有全非空（且都是合法仓库），这里直接收口。
    op.execute(sa.text("ALTER TABLE shipping_records ALTER COLUMN warehouse_id SET NOT NULL;"))

    op.create_foreign_key(
        "fk_shipping_records_warehouse_id",
        "shipping_records",
        "warehouses",
        ["warehouse_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # 5) shipping_provider_id 收口：NOT NULL
    op.execute(sa.text("ALTER TABLE shipping_records ALTER COLUMN shipping_provider_id SET NOT NULL;"))

    # 6) 硬幂等：unique(platform, shop_id, order_ref)
    op.create_unique_constraint(
        "uq_shipping_records_platform_shop_ref",
        "shipping_records",
        ["platform", "shop_id", "order_ref"],
    )

    # 7) tracking_no 非空时：同 carrier 下唯一（避免同一承运商重复运单号）
    # 注意：tracking_no 允许为空（你们存在先落记录后补运单号的场景）
    op.create_index(
        "uq_shipping_records_carrier_tracking_notnull",
        "shipping_records",
        ["carrier_code", "tracking_no"],
        unique=True,
        postgresql_where=sa.text("tracking_no IS NOT NULL"),
    )


def downgrade() -> None:
    # 反向撤销约束（不删除数据，不删除 FAKE provider）
    op.drop_index("uq_shipping_records_carrier_tracking_notnull", table_name="shipping_records")
    op.drop_constraint("uq_shipping_records_platform_shop_ref", "shipping_records", type_="unique")

    op.execute(sa.text("ALTER TABLE shipping_records ALTER COLUMN shipping_provider_id DROP NOT NULL;"))

    op.drop_constraint("fk_shipping_records_warehouse_id", "shipping_records", type_="foreignkey")
    op.execute(sa.text("ALTER TABLE shipping_records ALTER COLUMN warehouse_id DROP NOT NULL;"))
