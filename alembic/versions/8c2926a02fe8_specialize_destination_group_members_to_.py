"""specialize destination_group_members to province only

Revision ID: 8c2926a02fe8
Revises: 00abf0811392
Create Date: 2026-03-07 17:57:31.662490
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8c2926a02fe8"
down_revision: Union[str, Sequence[str], None] = "00abf0811392"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "shipping_provider_destination_group_members"

CK_SCOPE_VALID = "ck_sp_dest_group_members_scope_valid"
CK_SCOPE_FIELDS = "ck_sp_dest_group_members_scope_fields"

IDX_SCOPE_PROVINCE = "ix_spdgm_scope_province"
IDX_SCOPE_CITY = "ix_spdgm_scope_city"
IDX_UNIQUE_SCOPE_KEY = "uq_spdgm_group_scope_key"

IDX_PROVINCE = "ix_spdgm_group_province"
UQ_GROUP_PROVINCE = "uq_spdgm_group_province_key"


def upgrade() -> None:
    """
    Phase: destination_group_members 专用化
    - 删除 scope / city 字段
    - 只保留 province
    """

    conn = op.get_bind()

    # 1️⃣ 防止误迁移：检测是否存在 city/scope 数据
    rows = conn.execute(
        sa.text(
            f"""
            SELECT id, group_id, scope, province_name, city_name
            FROM {TABLE}
            WHERE scope <> 'province'
               OR city_code IS NOT NULL
               OR city_name IS NOT NULL
            LIMIT 20
            """
        )
    ).fetchall()

    if rows:
        raise RuntimeError(
            "Migration blocked: destination_group_members still contains city/scope data.\n"
            f"Example rows: {rows}"
        )

    # 2️⃣ 删除旧约束
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {CK_SCOPE_FIELDS}")
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {CK_SCOPE_VALID}")

    # 3️⃣ 删除旧索引
    op.execute(f"DROP INDEX IF EXISTS {IDX_UNIQUE_SCOPE_KEY}")
    op.execute(f"DROP INDEX IF EXISTS {IDX_SCOPE_CITY}")
    op.execute(f"DROP INDEX IF EXISTS {IDX_SCOPE_PROVINCE}")

    # 4️⃣ 删除字段
    op.drop_column(TABLE, "scope")
    op.drop_column(TABLE, "city_code")
    op.drop_column(TABLE, "city_name")

    # 5️⃣ 新约束：必须有 province
    op.create_check_constraint(
        "ck_sp_dest_group_members_province_required",
        TABLE,
        "(province_name IS NOT NULL OR province_code IS NOT NULL)",
    )

    # 6️⃣ 新唯一索引
    op.create_index(
        UQ_GROUP_PROVINCE,
        TABLE,
        [
            "group_id",
            sa.text("COALESCE(province_code, '')"),
            sa.text("COALESCE(province_name, '')"),
        ],
        unique=True,
    )

    # 7️⃣ 查询索引
    op.create_index(
        IDX_PROVINCE,
        TABLE,
        ["group_id", "province_code", "province_name"],
    )


def downgrade() -> None:
    """
    回滚：恢复 scope / city 结构
    """

    # 1️⃣ 删除新索引
    op.drop_index(UQ_GROUP_PROVINCE, table_name=TABLE)
    op.drop_index(IDX_PROVINCE, table_name=TABLE)

    op.execute(
        f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS ck_sp_dest_group_members_province_required"
    )

    # 2️⃣ 恢复字段
    op.add_column(TABLE, sa.Column("scope", sa.String(length=16), nullable=True))
    op.add_column(TABLE, sa.Column("city_code", sa.String(length=32), nullable=True))
    op.add_column(TABLE, sa.Column("city_name", sa.String(length=64), nullable=True))

    # 3️⃣ 填充默认 scope
    op.execute(
        f"""
        UPDATE {TABLE}
        SET scope = 'province',
            city_code = NULL,
            city_name = NULL
        WHERE scope IS NULL
        """
    )

    op.alter_column(TABLE, "scope", nullable=False)

    # 4️⃣ 恢复旧约束
    op.create_check_constraint(
        CK_SCOPE_VALID,
        TABLE,
        "scope in ('province','city')",
    )

    op.create_check_constraint(
        CK_SCOPE_FIELDS,
        TABLE,
        """
        (
          scope = 'province'
          AND (province_name IS NOT NULL OR province_code IS NOT NULL)
          AND city_name IS NULL
          AND city_code IS NULL
        )
        OR
        (
          scope = 'city'
          AND (province_name IS NOT NULL OR province_code IS NOT NULL)
          AND (city_name IS NOT NULL OR city_code IS NOT NULL)
        )
        """,
    )

    # 5️⃣ 恢复旧索引
    op.create_index(
        IDX_SCOPE_PROVINCE,
        TABLE,
        ["scope", "province_code", "province_name"],
    )

    op.create_index(
        IDX_SCOPE_CITY,
        TABLE,
        ["scope", "province_code", "city_code", "province_name", "city_name"],
    )

    op.create_index(
        IDX_UNIQUE_SCOPE_KEY,
        TABLE,
        [
            "group_id",
            sa.text("scope"),
            sa.text("COALESCE(province_code,'')"),
            sa.text("COALESCE(city_code,'')"),
            sa.text("COALESCE(province_name,'')"),
            sa.text("COALESCE(city_name,'')"),
        ],
        unique=True,
    )
