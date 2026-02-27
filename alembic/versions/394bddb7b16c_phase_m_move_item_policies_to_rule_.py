"""phase_m: move item policies to rule layer and freeze to lots; drop batch_code date gate

Revision ID: 394bddb7b16c
Revises: 58ab06bc364c
Create Date: 2026-02-27 10:37:03.800919

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '394bddb7b16c'
down_revision: Union[str, Sequence[str], None] = '58ab06bc364c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Phase M（一步到位版本）：
    1) 引入 items 规则层字段（policy）
    2) 将 policy 冻结到 lots（snapshot）
    3) 移除 inbound_receipt_lines 旧的 batch_code 日期门禁
    """

    # ---------------------------------------------------------------------
    # 1️⃣ 创建 ENUM 类型（若不存在）
    # ---------------------------------------------------------------------
    op.execute(
        """
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'lot_source_policy') THEN
    CREATE TYPE lot_source_policy AS ENUM ('INTERNAL_ONLY','SUPPLIER_ONLY');
  END IF;
END $$;
"""
    )

    op.execute(
        """
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'expiry_policy') THEN
    CREATE TYPE expiry_policy AS ENUM ('NONE','REQUIRED');
  END IF;
END $$;
"""
    )

    # ---------------------------------------------------------------------
    # 2️⃣ items：新增规则层字段
    # ---------------------------------------------------------------------
    op.add_column(
        "items",
        sa.Column(
            "lot_source_policy",
            sa.Enum("INTERNAL_ONLY", "SUPPLIER_ONLY", name="lot_source_policy"),
            nullable=True,
        ),
    )

    op.add_column(
        "items",
        sa.Column(
            "expiry_policy",
            sa.Enum("NONE", "REQUIRED", name="expiry_policy"),
            nullable=True,
        ),
    )

    op.add_column(
        "items",
        sa.Column("derivation_allowed", sa.Boolean(), nullable=True),
    )

    op.add_column(
        "items",
        sa.Column("uom_governance_enabled", sa.Boolean(), nullable=True),
    )

    # 回填（测试环境一步到位）
    op.execute(
        """
UPDATE items
SET
  lot_source_policy = COALESCE(lot_source_policy, 'SUPPLIER_ONLY'::lot_source_policy),
  expiry_policy = COALESCE(
    expiry_policy,
    CASE
      WHEN has_shelf_life THEN 'REQUIRED'::expiry_policy
      ELSE 'NONE'::expiry_policy
    END
  ),
  derivation_allowed = COALESCE(derivation_allowed, TRUE),
  uom_governance_enabled = COALESCE(uom_governance_enabled, FALSE);
"""
    )

    # 强制 NOT NULL（规则层封板）
    op.alter_column("items", "lot_source_policy", nullable=False)
    op.alter_column("items", "expiry_policy", nullable=False)
    op.alter_column("items", "derivation_allowed", nullable=False)
    op.alter_column("items", "uom_governance_enabled", nullable=False)

    # policy 与 shelf_life 参数一致性（禁止“隐式规则”）
    op.create_check_constraint(
        "ck_items_expiry_policy_vs_shelf_life",
        "items",
        "(expiry_policy = 'REQUIRED'::expiry_policy) "
        "OR (shelf_life_value IS NULL AND shelf_life_unit IS NULL)",
    )

    # ---------------------------------------------------------------------
    # 3️⃣ lots：冻结 policy snapshot（防未来规则漂移）
    # ---------------------------------------------------------------------
    op.add_column(
        "lots",
        sa.Column(
            "item_lot_source_policy_snapshot",
            sa.Enum("INTERNAL_ONLY", "SUPPLIER_ONLY", name="lot_source_policy"),
            nullable=True,
        ),
    )

    op.add_column(
        "lots",
        sa.Column(
            "item_expiry_policy_snapshot",
            sa.Enum("NONE", "REQUIRED", name="expiry_policy"),
            nullable=True,
        ),
    )

    op.add_column(
        "lots",
        sa.Column("item_derivation_allowed_snapshot", sa.Boolean(), nullable=True),
    )

    op.add_column(
        "lots",
        sa.Column("item_uom_governance_enabled_snapshot", sa.Boolean(), nullable=True),
    )

    # 用当前 items.policy 回填历史 lot
    op.execute(
        """
UPDATE lots l
SET
  item_lot_source_policy_snapshot = COALESCE(item_lot_source_policy_snapshot, i.lot_source_policy),
  item_expiry_policy_snapshot = COALESCE(item_expiry_policy_snapshot, i.expiry_policy),
  item_derivation_allowed_snapshot = COALESCE(item_derivation_allowed_snapshot, i.derivation_allowed),
  item_uom_governance_enabled_snapshot = COALESCE(item_uom_governance_enabled_snapshot, i.uom_governance_enabled)
FROM items i
WHERE i.id = l.item_id;
"""
    )

    # 新 lot 必须冻结 policy
    op.alter_column("lots", "item_lot_source_policy_snapshot", nullable=False)
    op.alter_column("lots", "item_expiry_policy_snapshot", nullable=False)
    op.alter_column("lots", "item_derivation_allowed_snapshot", nullable=False)
    op.alter_column("lots", "item_uom_governance_enabled_snapshot", nullable=False)

    # ---------------------------------------------------------------------
    # 4️⃣ inbound_receipt_lines：移除 batch_code 日期门禁
    # ---------------------------------------------------------------------
    op.drop_constraint(
        "ck_inbound_receipt_lines_batch_null_dates_null",
        "inbound_receipt_lines",
        type_="check",
    )

    # 改为纯“行内一致性”约束
    op.create_check_constraint(
        "ck_inbound_receipt_lines_prod_le_exp",
        "inbound_receipt_lines",
        "production_date IS NULL "
        "OR expiry_date IS NULL "
        "OR production_date <= expiry_date",
    )


def downgrade() -> None:
    """
    反向迁移（测试环境可用）。
    """

    # 恢复 receipt_lines 原门禁
    op.drop_constraint(
        "ck_inbound_receipt_lines_prod_le_exp",
        "inbound_receipt_lines",
        type_="check",
    )

    op.create_check_constraint(
        "ck_inbound_receipt_lines_batch_null_dates_null",
        "inbound_receipt_lines",
        "(batch_code IS NOT NULL) "
        "OR (production_date IS NULL AND expiry_date IS NULL)",
    )

    # 移除 lots snapshot
    op.drop_column("lots", "item_uom_governance_enabled_snapshot")
    op.drop_column("lots", "item_derivation_allowed_snapshot")
    op.drop_column("lots", "item_expiry_policy_snapshot")
    op.drop_column("lots", "item_lot_source_policy_snapshot")

    # 移除 items 规则字段
    op.drop_constraint("ck_items_expiry_policy_vs_shelf_life", "items", type_="check")
    op.drop_column("items", "uom_governance_enabled")
    op.drop_column("items", "derivation_allowed")
    op.drop_column("items", "expiry_policy")
    op.drop_column("items", "lot_source_policy")

    # 删除 enum
    op.execute("DROP TYPE IF EXISTS expiry_policy;")
    op.execute("DROP TYPE IF EXISTS lot_source_policy;")
