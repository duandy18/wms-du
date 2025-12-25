"""create_shipping_provider_contacts

Revision ID: f213ac3821b2
Revises: 2da444804c8f
Create Date: 2025-12-13 16:39:48.483530
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f213ac3821b2"
down_revision: Union[str, Sequence[str], None] = "2da444804c8f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Shipping Providers 联系人子表（Phase 3 延展）

    目标：
    - 结构 100% 对齐 supplier_contacts
    - 支持多联系人
    - 同一 shipping_provider 仅允许一个主联系人（部分唯一索引）
    - FK 一律 RESTRICT，禁止级联误删
    - 从 legacy 单联系人列进行一次性回填
    """

    # 1) 创建 shipping_provider_contacts 表
    op.create_table(
        "shipping_provider_contacts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),

        sa.Column("shipping_provider_id", sa.Integer(), nullable=False),

        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("wechat", sa.String(length=64), nullable=True),

        sa.Column(
            "role",
            sa.String(length=32),
            nullable=False,
            server_default="other",
            comment="shipping / billing / after_sales / other",
        ),
        sa.Column(
            "is_primary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),

        sa.ForeignKeyConstraint(
            ["shipping_provider_id"],
            ["shipping_providers.id"],
            name="fk_shipping_provider_contacts_provider_id",
            ondelete="RESTRICT",
        ),
    )

    # 2) 同一 provider 只允许一个主联系人（部分唯一索引）
    op.create_index(
        "uq_shipping_provider_contacts_primary",
        "shipping_provider_contacts",
        ["shipping_provider_id"],
        unique=True,
        postgresql_where=sa.text("is_primary IS TRUE"),
    )

    # 3) legacy 单联系人列 → 回填为主联系人
    #
    # 规则：
    # - 只要 legacy 字段里“有任何一个不为空”，就生成一个主联系人
    # - name 优先使用 contact_name；为空则回退为 provider.name
    # - role 固定为 shipping
    #
    op.execute(
        """
        INSERT INTO shipping_provider_contacts
          (shipping_provider_id, name, phone, email, wechat, role, is_primary, active)
        SELECT
          s.id,
          COALESCE(NULLIF(trim(s.contact_name), ''), s.name) AS name,
          NULLIF(trim(s.phone), '') AS phone,
          NULLIF(trim(s.email), '') AS email,
          NULLIF(trim(s.wechat), '') AS wechat,
          'shipping' AS role,
          TRUE AS is_primary,
          TRUE AS active
        FROM shipping_providers s
        WHERE
          (s.contact_name IS NOT NULL AND trim(s.contact_name) <> '')
          OR (s.phone IS NOT NULL AND trim(s.phone) <> '')
          OR (s.email IS NOT NULL AND trim(s.email) <> '')
          OR (s.wechat IS NOT NULL AND trim(s.wechat) <> '');
        """
    )


def downgrade() -> None:
    """
    回滚策略：
    - 仅删除 contacts 表与索引
    - 不回写 legacy 列（避免覆盖历史人工修改）
    """

    op.drop_index(
        "uq_shipping_provider_contacts_primary",
        table_name="shipping_provider_contacts",
    )
    op.drop_table("shipping_provider_contacts")
