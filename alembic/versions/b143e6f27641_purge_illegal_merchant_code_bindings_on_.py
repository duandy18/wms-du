"""purge illegal merchant_code bindings on prod stores (test items)

Revision ID: b143e6f27641
Revises: 87e57bf35cc0
Create Date: 2026-02-15

删除历史遗留非法绑定：

条件：
1) 店铺为 PROD（stores.id 不在 platform_test_shops(code='DEFAULT') 中）
2) merchant_code_fsku_bindings 绑定到的 FSKU 展开后包含 DEFAULT Test Set 商品

动作：
- 直接 DELETE merchant_code_fsku_bindings 行
- 迁移结束后断言必须归零（fail-fast）

不可逆：downgrade 不恢复已删除数据
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "b143e6f27641"
down_revision: Union[str, Sequence[str], None] = "87e57bf35cc0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1️⃣ 删除非法绑定
    conn.execute(
        sa.text(
            """
            WITH default_set AS (
              SELECT id AS set_id
                FROM item_test_sets
               WHERE code = 'DEFAULT'
               LIMIT 1
            ),
            prod_stores AS (
              SELECT s.platform, s.shop_id
                FROM stores s
               WHERE NOT EXISTS (
                 SELECT 1
                   FROM platform_test_shops pts
                  WHERE pts.store_id = s.id
                    AND pts.code = 'DEFAULT'
               )
            ),
            illegal_ids AS (
              SELECT b.id
                FROM merchant_code_fsku_bindings b
                JOIN prod_stores ps
                  ON upper(ps.platform) = upper(b.platform)
                 AND btrim(CAST(ps.shop_id AS text)) = btrim(CAST(b.shop_id AS text))
               WHERE EXISTS (
                 SELECT 1
                   FROM fsku_components c
                   JOIN item_test_set_items tsi
                     ON tsi.item_id = c.item_id
                   JOIN default_set ds
                     ON ds.set_id = tsi.set_id
                  WHERE c.fsku_id = b.fsku_id
               )
            )
            DELETE FROM merchant_code_fsku_bindings b
             USING illegal_ids x
             WHERE b.id = x.id;
            """
        )
    )

    # 2️⃣ 断言：必须归零
    left = conn.execute(
        sa.text(
            """
            WITH default_set AS (
              SELECT id AS set_id
                FROM item_test_sets
               WHERE code = 'DEFAULT'
               LIMIT 1
            ),
            prod_stores AS (
              SELECT s.platform, s.shop_id
                FROM stores s
               WHERE NOT EXISTS (
                 SELECT 1
                   FROM platform_test_shops pts
                  WHERE pts.store_id = s.id
                    AND pts.code = 'DEFAULT'
               )
            )
            SELECT COUNT(*)
              FROM merchant_code_fsku_bindings b
              JOIN prod_stores ps
                ON upper(ps.platform) = upper(b.platform)
               AND btrim(CAST(ps.shop_id AS text)) = btrim(CAST(b.shop_id AS text))
             WHERE EXISTS (
               SELECT 1
                 FROM fsku_components c
                 JOIN item_test_set_items tsi
                   ON tsi.item_id = c.item_id
                 JOIN default_set ds
                   ON ds.set_id = tsi.set_id
                WHERE c.fsku_id = b.fsku_id
             );
            """
        )
    ).scalar_one()

    if int(left) != 0:
        raise RuntimeError(
            f"purge illegal merchant_code bindings failed: still left={left}"
        )


def downgrade() -> None:
    # 不恢复历史绑定（数据清洗不可逆）
    pass
