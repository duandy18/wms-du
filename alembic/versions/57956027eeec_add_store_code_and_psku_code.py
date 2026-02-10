"""add_store_code_and_psku_code

Revision ID: 57956027eeec
Revises: 51d23f377b32
Create Date: 2026-02-09 18:31:40.273699

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "57956027eeec"
down_revision: Union[str, Sequence[str], None] = "51d23f377b32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- 1) stores.store_code ---
    op.add_column("stores", sa.Column("store_code", sa.String(length=32), nullable=True))

    # 回填：先用稳定短码 S{id}（避免 NULL）
    op.execute("UPDATE stores SET store_code = 'S' || id WHERE store_code IS NULL")

    # 设为 NOT NULL
    op.alter_column("stores", "store_code", existing_type=sa.String(length=32), nullable=False)

    # 同平台下唯一（跨平台可重复）
    op.create_unique_constraint("uq_stores_platform_store_code", "stores", ["platform", "store_code"])

    # --- 2) platform_sku_bindings: psku_code + psku_rule_version ---
    op.add_column("platform_sku_bindings", sa.Column("psku_code", sa.String(length=128), nullable=True))
    op.add_column("platform_sku_bindings", sa.Column("psku_rule_version", sa.Integer(), nullable=True))

    # 仅对 current 且 fsku_id 不为空的绑定回填（legacy item_id 绑定不回填）
    # 规则：PSKU_CODE_V1 = UPPER(platform) || '-' || store_code || '-' || fsku.code
    #
    # ⚠️ Postgres 限制：不要在 FROM 子句的 JOIN ... ON 中引用被 UPDATE 的表别名 b
    #    否则可能报 invalid reference to FROM-clause entry for table "b"
    op.execute(
        """
        UPDATE platform_sku_bindings AS b
           SET psku_code = upper(b.platform) || '-' || s.store_code || '-' || f.code,
               psku_rule_version = 1
          FROM stores AS s,
               fskus  AS f
         WHERE b.store_id = s.id
           AND b.fsku_id = f.id
           AND b.fsku_id IS NOT NULL
           AND b.effective_to IS NULL
        """
    )


def downgrade() -> None:
    # 反向删除（先删 bindings 字段，再删 stores 约束与字段）
    op.drop_column("platform_sku_bindings", "psku_rule_version")
    op.drop_column("platform_sku_bindings", "psku_code")

    op.drop_constraint("uq_stores_platform_store_code", "stores", type_="unique")
    op.drop_column("stores", "store_code")
