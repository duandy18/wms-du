"""shipment shipping_records add package_no and switch to package-level unique key

Revision ID: 0c00db920758
Revises: c2475957c0c9
Create Date: 2026-03-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = "0c00db920758"
down_revision: Union[str, Sequence[str], None] = "c2475957c0c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ✅ 1. 新增 package_no
    op.add_column(
        "shipping_records",
        sa.Column(
            "package_no",
            sa.Integer(),
            nullable=False,
            server_default="1",  # 临时默认值，避免旧数据报错
            comment="包裹序号，从 1 开始，对应 order_shipment_prepare_packages.package_no",
        ),
    )

    # ✅ 2. 删除旧唯一约束（订单级）
    op.drop_constraint(
        "uq_shipping_records_platform_shop_ref",
        "shipping_records",
        type_="unique",
    )

    # ✅ 3. 新唯一约束（订单 + 包裹）
    op.create_unique_constraint(
        "uq_shipping_records_platform_shop_ref_package",
        "shipping_records",
        ["platform", "shop_id", "order_ref", "package_no"],
    )

    # ✅ 4. 清理默认值（防止误用）
    op.alter_column(
        "shipping_records",
        "package_no",
        server_default=None,
    )


def downgrade() -> None:
    # 回滚逻辑（简单还原）
    op.drop_constraint(
        "uq_shipping_records_platform_shop_ref_package",
        "shipping_records",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_shipping_records_platform_shop_ref",
        "shipping_records",
        ["platform", "shop_id", "order_ref"],
    )

    op.drop_column("shipping_records", "package_no")
