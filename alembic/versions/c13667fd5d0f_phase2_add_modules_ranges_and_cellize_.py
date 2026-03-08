"""phase2_add_modules_ranges_and_cellize_matrix

Revision ID: c13667fd5d0f
Revises: cbd71bffa819
Create Date: 2026-03-08 14:22:45.690383

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c13667fd5d0f"
down_revision: Union[str, Sequence[str], None] = "cbd71bffa819"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --------------------------------------------------
    # 1 创建 modules 表
    # --------------------------------------------------
    op.create_table(
        "shipping_provider_pricing_scheme_modules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scheme_id", sa.Integer(), nullable=False),
        sa.Column("module_code", sa.String(16), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["scheme_id"],
            ["shipping_provider_pricing_schemes.id"],
            ondelete="CASCADE",
            name="fk_sppsm_scheme_id",
        ),
        sa.CheckConstraint(
            "module_code in ('standard','other')",
            name="ck_sppsm_module_code_valid",
        ),
        sa.UniqueConstraint("scheme_id", "module_code", name="uq_sppsm_scheme_module_code"),
        sa.UniqueConstraint("scheme_id", "sort_order", name="uq_sppsm_scheme_sort_order"),
    )

    # --------------------------------------------------
    # 2 创建 ranges 表
    # --------------------------------------------------
    op.create_table(
        "shipping_provider_pricing_scheme_module_ranges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("module_id", sa.Integer(), nullable=False),
        sa.Column("min_kg", sa.Numeric(10, 3), nullable=False),
        sa.Column("max_kg", sa.Numeric(10, 3), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["shipping_provider_pricing_scheme_modules.id"],
            ondelete="CASCADE",
            name="fk_sppsmr_module_id",
        ),
        sa.CheckConstraint(
            "min_kg >= 0 AND (max_kg IS NULL OR max_kg > min_kg)",
            name="ck_sppsmr_range_valid",
        ),
        sa.UniqueConstraint("module_id", "sort_order", name="uq_sppsmr_module_sort_order"),
        sa.UniqueConstraint("module_id", "min_kg", "max_kg", name="uq_sppsmr_module_range"),
    )

    # 复合外键需要被引用端存在唯一键
    op.create_unique_constraint(
        "uq_sppsmr_id_module",
        "shipping_provider_pricing_scheme_module_ranges",
        ["id", "module_id"],
    )

    # 防止同一 module 下出现多个 open-ended range（max_kg IS NULL）
    op.create_index(
        "uq_sppsmr_module_open_ended",
        "shipping_provider_pricing_scheme_module_ranges",
        ["module_id", "min_kg"],
        unique=True,
        postgresql_where=sa.text("max_kg IS NULL"),
    )

    # --------------------------------------------------
    # 3 destination_groups 新列
    # --------------------------------------------------
    with op.batch_alter_table("shipping_provider_destination_groups") as batch_op:
        batch_op.add_column(sa.Column("module_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"))

    op.create_foreign_key(
        "fk_dest_group_module",
        "shipping_provider_destination_groups",
        "shipping_provider_pricing_scheme_modules",
        ["module_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # --------------------------------------------------
    # 4 pricing_matrix 新列
    # --------------------------------------------------
    with op.batch_alter_table("shipping_provider_pricing_matrix") as batch_op:
        batch_op.add_column(sa.Column("module_range_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("range_module_id", sa.Integer(), nullable=True))

    op.create_foreign_key(
        "fk_pricing_matrix_range",
        "shipping_provider_pricing_matrix",
        "shipping_provider_pricing_scheme_module_ranges",
        ["module_range_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # --------------------------------------------------
    # 5 为每个 scheme 创建 standard / other modules
    # --------------------------------------------------
    op.execute(
        """
        INSERT INTO shipping_provider_pricing_scheme_modules
            (scheme_id, module_code, name, sort_order)
        SELECT id, 'standard', '标准区域', 0
          FROM shipping_provider_pricing_schemes
        """
    )

    op.execute(
        """
        INSERT INTO shipping_provider_pricing_scheme_modules
            (scheme_id, module_code, name, sort_order)
        SELECT id, 'other', '其他区域', 1
          FROM shipping_provider_pricing_schemes
        """
    )

    # --------------------------------------------------
    # 6 现有 groups 先全部归到 standard module
    # --------------------------------------------------
    op.execute(
        """
        UPDATE shipping_provider_destination_groups g
           SET module_id = m.id
          FROM shipping_provider_pricing_scheme_modules m
         WHERE g.scheme_id = m.scheme_id
           AND m.module_code = 'standard'
        """
    )

    op.execute(
        """
        WITH ranked AS (
            SELECT g.id,
                   ROW_NUMBER() OVER (PARTITION BY g.module_id ORDER BY g.id) - 1 AS rn
              FROM shipping_provider_destination_groups g
        )
        UPDATE shipping_provider_destination_groups g
           SET sort_order = ranked.rn
          FROM ranked
         WHERE g.id = ranked.id
        """
    )

    # --------------------------------------------------
    # 7 从旧 pricing_matrix(min/max) 生成 ranges
    # --------------------------------------------------
    op.execute(
        """
        INSERT INTO shipping_provider_pricing_scheme_module_ranges
            (module_id, min_kg, max_kg, sort_order)
        SELECT
            t.module_id,
            t.min_kg,
            t.max_kg,
            ROW_NUMBER() OVER (
                PARTITION BY t.module_id
                ORDER BY t.min_kg ASC, t.max_kg ASC NULLS LAST
            ) - 1 AS sort_order
        FROM (
            SELECT DISTINCT
                   m.id AS module_id,
                   pm.min_kg,
                   pm.max_kg
              FROM shipping_provider_pricing_matrix pm
              JOIN shipping_provider_destination_groups g
                ON g.id = pm.group_id
              JOIN shipping_provider_pricing_scheme_modules m
                ON m.id = g.module_id
        ) AS t
        """
    )

    # --------------------------------------------------
    # 8 pricing_matrix 绑定到新 range
    # --------------------------------------------------
    op.execute(
        """
        UPDATE shipping_provider_pricing_matrix pm
           SET module_range_id = r.id
          FROM shipping_provider_destination_groups g,
               shipping_provider_pricing_scheme_module_ranges r
         WHERE pm.group_id = g.id
           AND r.module_id = g.module_id
           AND r.min_kg = pm.min_kg
           AND (
                r.max_kg = pm.max_kg
                OR (r.max_kg IS NULL AND pm.max_kg IS NULL)
           )
        """
    )

    # 为复合外键回填 range_module_id
    op.execute(
        """
        UPDATE shipping_provider_pricing_matrix pm
           SET range_module_id = r.module_id
          FROM shipping_provider_pricing_scheme_module_ranges r
         WHERE pm.module_range_id = r.id
        """
    )

    # --------------------------------------------------
    # 9 设置 NOT NULL
    # --------------------------------------------------
    with op.batch_alter_table("shipping_provider_destination_groups") as batch_op:
        batch_op.alter_column("module_id", existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table("shipping_provider_pricing_matrix") as batch_op:
        batch_op.alter_column("module_range_id", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("range_module_id", existing_type=sa.Integer(), nullable=False)

    # 给 destination_groups 增加复合唯一键，供复合外键引用
    op.create_unique_constraint(
        "uq_spdg_id_module",
        "shipping_provider_destination_groups",
        ["id", "module_id"],
    )

    # --------------------------------------------------
    # 10 删除旧依赖约束
    # --------------------------------------------------
    # 老 exclusion constraint 依赖 min_kg / max_kg，必须先删
    op.execute(
        """
        ALTER TABLE shipping_provider_pricing_matrix
        DROP CONSTRAINT IF EXISTS excl_sppm_active_group_weight_range_no_overlap
        """
    )

    # 旧唯一约束若存在也先删，避免后续新唯一冲突
    op.execute(
        """
        ALTER TABLE shipping_provider_pricing_matrix
        DROP CONSTRAINT IF EXISTS uq_sppm_group_module_range
        """
    )

    # --------------------------------------------------
    # 11 增加“同模块一致性”复合外键
    # --------------------------------------------------
    op.create_foreign_key(
        "fk_sppm_group_same_module",
        "shipping_provider_pricing_matrix",
        "shipping_provider_destination_groups",
        ["group_id", "range_module_id"],
        ["id", "module_id"],
        ondelete="CASCADE",
    )

    op.create_foreign_key(
        "fk_sppm_range_same_module",
        "shipping_provider_pricing_matrix",
        "shipping_provider_pricing_scheme_module_ranges",
        ["module_range_id", "range_module_id"],
        ["id", "module_id"],
        ondelete="CASCADE",
    )

    # --------------------------------------------------
    # 12 重建 pricing_matrix 约束（终态）
    # --------------------------------------------------
    op.execute(
        """
        ALTER TABLE shipping_provider_pricing_matrix
        DROP CONSTRAINT IF EXISTS ck_sppm_range_valid
        """
    )
    op.execute(
        """
        ALTER TABLE shipping_provider_pricing_matrix
        DROP CONSTRAINT IF EXISTS ck_sppm_mode_valid
        """
    )
    op.execute(
        """
        ALTER TABLE shipping_provider_pricing_matrix
        DROP CONSTRAINT IF EXISTS ck_sppm_flat_shape
        """
    )
    op.execute(
        """
        ALTER TABLE shipping_provider_pricing_matrix
        DROP CONSTRAINT IF EXISTS ck_sppm_linear_total_shape
        """
    )
    op.execute(
        """
        ALTER TABLE shipping_provider_pricing_matrix
        DROP CONSTRAINT IF EXISTS ck_sppm_step_over_shape
        """
    )
    op.execute(
        """
        ALTER TABLE shipping_provider_pricing_matrix
        DROP CONSTRAINT IF EXISTS ck_sppm_manual_quote_shape
        """
    )

    op.create_check_constraint(
        "ck_sppm_mode_valid",
        "shipping_provider_pricing_matrix",
        "pricing_mode in ('flat','linear_total','step_over','manual_quote')",
    )
    op.create_check_constraint(
        "ck_sppm_flat_shape",
        "shipping_provider_pricing_matrix",
        """
        pricing_mode <> 'flat'
        OR (
            flat_amount IS NOT NULL
            AND base_amount IS NULL
            AND rate_per_kg IS NULL
            AND base_kg IS NULL
        )
        """,
    )
    op.create_check_constraint(
        "ck_sppm_linear_total_shape",
        "shipping_provider_pricing_matrix",
        """
        pricing_mode <> 'linear_total'
        OR (
            flat_amount IS NULL
            AND base_amount IS NOT NULL
            AND rate_per_kg IS NOT NULL
            AND base_kg IS NULL
        )
        """,
    )
    op.create_check_constraint(
        "ck_sppm_step_over_shape",
        "shipping_provider_pricing_matrix",
        """
        pricing_mode <> 'step_over'
        OR (
            flat_amount IS NULL
            AND base_kg IS NOT NULL
            AND base_amount IS NOT NULL
            AND rate_per_kg IS NOT NULL
        )
        """,
    )
    op.create_check_constraint(
        "ck_sppm_manual_quote_shape",
        "shipping_provider_pricing_matrix",
        """
        pricing_mode <> 'manual_quote'
        OR (
            flat_amount IS NULL
            AND base_amount IS NULL
            AND rate_per_kg IS NULL
            AND base_kg IS NULL
        )
        """,
    )

    op.create_unique_constraint(
        "uq_sppm_group_module_range",
        "shipping_provider_pricing_matrix",
        ["group_id", "module_range_id"],
    )

    # --------------------------------------------------
    # 13 删除旧 min/max 列
    # --------------------------------------------------
    with op.batch_alter_table("shipping_provider_pricing_matrix") as batch_op:
        batch_op.drop_column("min_kg")
        batch_op.drop_column("max_kg")

    # --------------------------------------------------
    # 14 destination_groups 终态唯一约束
    # --------------------------------------------------
    op.execute(
        """
        ALTER TABLE shipping_provider_destination_groups
        DROP CONSTRAINT IF EXISTS uq_sp_dest_groups_scheme_name
        """
    )

    op.create_unique_constraint(
        "uq_sp_dest_groups_module_name",
        "shipping_provider_destination_groups",
        ["module_id", "name"],
    )
    op.create_unique_constraint(
        "uq_sp_dest_groups_module_sort_order",
        "shipping_provider_destination_groups",
        ["module_id", "sort_order"],
    )


def downgrade() -> None:
    raise RuntimeError(
        "Irreversible migration: module/range matrix architecture enabled."
    )
