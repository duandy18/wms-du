"""finalize_shipping_provider_surcharges_scope

Revision ID: d1a2e080a1dc
Revises: ff7ddf02de26
Create Date: 2026-03-07 12:56:16.216580

目标：
- 删除 shipping_provider_surcharges.priority
- 删除 shipping_provider_surcharges.stackable
- 删除 scope='always' 语义，仅保留 province / city
- 重建 scope 相关 CHECK 约束

注意：
- 若库中仍存在 scope='always' 的旧数据，本 migration 会直接失败
  需要先人工清理或迁移这些数据，再重跑
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


# revision identifiers, used by Alembic.
revision: str = "d1a2e080a1dc"
down_revision: Union[str, Sequence[str], None] = "ff7ddf02de26"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "shipping_provider_surcharges"


def _has_column(insp, table_name: str, column_name: str) -> bool:
    cols = insp.get_columns(table_name)
    return any(c["name"] == column_name for c in cols)


def _has_index(insp, table_name: str, index_name: str) -> bool:
    idxs = insp.get_indexes(table_name)
    return any(i["name"] == index_name for i in idxs)


def _has_check(bind, table_name: str, check_name: str) -> bool:
    sql = text(
        """
        SELECT 1
          FROM information_schema.table_constraints
         WHERE table_name = :table_name
           AND constraint_type = 'CHECK'
           AND constraint_name = :check_name
         LIMIT 1
        """
    )
    row = bind.execute(sql, {"table_name": table_name, "check_name": check_name}).first()
    return row is not None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    insp = inspect(bind)

    # 防止 silently 破坏旧数据语义
    if _has_column(insp, TABLE, "scope"):
        always_count = bind.execute(
            text(
                f"""
                SELECT COUNT(*)
                  FROM {TABLE}
                 WHERE BTRIM(COALESCE(scope, '')) = 'always'
                """
            )
        ).scalar_one()
        if int(always_count or 0) > 0:
            raise RuntimeError(
                "Migration blocked: shipping_provider_surcharges still contains scope='always' rows. "
                "Please clean or migrate them manually before upgrading."
            )

    # 先删旧约束
    for ck_name in (
        "ck_sp_surcharges_scope_fields",
        "ck_sp_surcharges_scope_valid",
    ):
        if _has_check(bind, TABLE, ck_name):
            op.drop_constraint(ck_name, TABLE, type_="check")

    # 删除旧索引 / 旧列
    if _has_index(insp, TABLE, "ix_sp_surcharges_scheme_active_priority"):
        op.drop_index("ix_sp_surcharges_scheme_active_priority", table_name=TABLE)

    if _has_column(insp, TABLE, "priority"):
        op.drop_column(TABLE, "priority")

    if _has_column(insp, TABLE, "stackable"):
        op.drop_column(TABLE, "stackable")

    # scope 列不再允许默认值 always
    if _has_column(insp, TABLE, "scope"):
        op.alter_column(
            TABLE,
            "scope",
            existing_type=sa.String(length=16),
            server_default=None,
            existing_nullable=False,
        )

    # 重建终态 CHECK 约束
    op.create_check_constraint(
        "ck_sp_surcharges_scope_valid",
        TABLE,
        "scope in ('province','city')",
    )

    op.create_check_constraint(
        "ck_sp_surcharges_scope_fields",
        TABLE,
        """
        (
          (scope = 'province'
            AND (province_name IS NOT NULL OR province_code IS NOT NULL)
            AND city_name IS NULL
            AND city_code IS NULL
          )
          OR
          (scope = 'city'
            AND (province_name IS NOT NULL OR province_code IS NOT NULL)
            AND (city_name IS NOT NULL OR city_code IS NOT NULL)
          )
        )
        """,
    )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    insp = inspect(bind)

    # 删除新约束
    for ck_name in (
        "ck_sp_surcharges_scope_fields",
        "ck_sp_surcharges_scope_valid",
    ):
        if _has_check(bind, TABLE, ck_name):
            op.drop_constraint(ck_name, TABLE, type_="check")

    # 恢复旧列
    if not _has_column(insp, TABLE, "priority"):
        op.add_column(
            TABLE,
            sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
        )

    if not _has_column(insp, TABLE, "stackable"):
        op.add_column(
            TABLE,
            sa.Column("stackable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )

    # 恢复旧索引
    if not _has_index(insp, TABLE, "ix_sp_surcharges_scheme_active_priority"):
        op.create_index(
            "ix_sp_surcharges_scheme_active_priority",
            TABLE,
            ["scheme_id", "active", "priority"],
        )

    # 恢复 scope 默认值
    op.alter_column(
        TABLE,
        "scope",
        existing_type=sa.String(length=16),
        server_default=sa.text("'always'"),
        existing_nullable=False,
    )

    # 恢复旧 CHECK
    op.create_check_constraint(
        "ck_sp_surcharges_scope_valid",
        TABLE,
        "scope in ('always','province','city')",
    )

    op.create_check_constraint(
        "ck_sp_surcharges_scope_fields",
        TABLE,
        """
        (
          (scope = 'always'
            AND province_name IS NULL
            AND city_name IS NULL
            AND province_code IS NULL
            AND city_code IS NULL
          )
          OR
          (scope = 'province'
            AND (province_name IS NOT NULL OR province_code IS NOT NULL)
            AND city_name IS NULL
            AND city_code IS NULL
          )
          OR
          (scope = 'city'
            AND (province_name IS NOT NULL OR province_code IS NOT NULL)
            AND (city_name IS NOT NULL OR city_code IS NOT NULL)
          )
        )
        """,
    )
