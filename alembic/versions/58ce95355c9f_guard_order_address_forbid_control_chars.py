"""guard(order_address): forbid control chars

Revision ID: 58ce95355c9f
Revises: 5e961df2e5e5
Create Date: 2026-02-13 16:51:16.653132
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "58ce95355c9f"
down_revision: Union[str, Sequence[str], None] = "5e961df2e5e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 禁止 order_address 中关键文本字段包含控制字符（\n \r \t）

    op.create_check_constraint(
        "ck_order_address_receiver_name_no_ctrl",
        "order_address",
        r"receiver_name IS NULL OR receiver_name !~ E'[\n\r\t]'",
    )

    op.create_check_constraint(
        "ck_order_address_receiver_phone_no_ctrl",
        "order_address",
        r"receiver_phone IS NULL OR receiver_phone !~ E'[\n\r\t]'",
    )

    op.create_check_constraint(
        "ck_order_address_province_no_ctrl",
        "order_address",
        r"province IS NULL OR province !~ E'[\n\r\t]'",
    )

    op.create_check_constraint(
        "ck_order_address_city_no_ctrl",
        "order_address",
        r"city IS NULL OR city !~ E'[\n\r\t]'",
    )

    op.create_check_constraint(
        "ck_order_address_district_no_ctrl",
        "order_address",
        r"district IS NULL OR district !~ E'[\n\r\t]'",
    )

    op.create_check_constraint(
        "ck_order_address_detail_no_ctrl",
        "order_address",
        r"detail IS NULL OR detail !~ E'[\n\r\t]'",
    )

    op.create_check_constraint(
        "ck_order_address_zipcode_no_ctrl",
        "order_address",
        r"zipcode IS NULL OR zipcode !~ E'[\n\r\t]'",
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint("ck_order_address_zipcode_no_ctrl", "order_address", type_="check")
    op.drop_constraint("ck_order_address_detail_no_ctrl", "order_address", type_="check")
    op.drop_constraint("ck_order_address_district_no_ctrl", "order_address", type_="check")
    op.drop_constraint("ck_order_address_city_no_ctrl", "order_address", type_="check")
    op.drop_constraint("ck_order_address_province_no_ctrl", "order_address", type_="check")
    op.drop_constraint("ck_order_address_receiver_phone_no_ctrl", "order_address", type_="check")
    op.drop_constraint("ck_order_address_receiver_name_no_ctrl", "order_address", type_="check")
