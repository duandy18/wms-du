"""shipping_providers: remove warehouse_id, enforce M2M binding"""

from typing import Sequence, Union
from alembic import op

revision: str = "ff30b9b8423c"
down_revision: Union[str, Sequence[str], None] = "fa3efdb244b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1️⃣ 补齐关系表
    op.execute(
        """
        INSERT INTO warehouse_shipping_providers
            (warehouse_id, shipping_provider_id, active, priority, created_at, updated_at)
        SELECT
            sp.warehouse_id,
            sp.id,
            TRUE,
            0,
            NOW(),
            NOW()
        FROM shipping_providers sp
        WHERE sp.warehouse_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM warehouse_shipping_providers w
              WHERE w.shipping_provider_id = sp.id
          );
        """
    )

    # 2️⃣ 删除 FK
    op.execute("""
        ALTER TABLE shipping_providers
        DROP CONSTRAINT IF EXISTS fk_shipping_providers_warehouse_id;
    """)

    # 3️⃣ 删除索引
    op.execute("""
        DROP INDEX IF EXISTS ix_shipping_providers_warehouse_id;
    """)

    # 4️⃣ 删除列
    op.execute("""
        ALTER TABLE shipping_providers
        DROP COLUMN IF EXISTS warehouse_id;
    """)

    # 5️⃣ 强制 code NOT NULL（模型已改）
    op.execute("""
        ALTER TABLE shipping_providers
        ALTER COLUMN code SET NOT NULL;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE shipping_providers
        ADD COLUMN warehouse_id INTEGER;
    """)

    op.execute("""
        ALTER TABLE shipping_providers
        ADD CONSTRAINT fk_shipping_providers_warehouse_id
        FOREIGN KEY (warehouse_id)
        REFERENCES warehouses(id)
        ON DELETE RESTRICT;
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_shipping_providers_warehouse_id
        ON shipping_providers (warehouse_id);
    """)

    op.execute("""
        ALTER TABLE shipping_providers
        ALTER COLUMN code DROP NOT NULL;
    """)
