from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8fce9c4b7a12"
down_revision: Union[str, Sequence[str], None] = "cfb8827b7de5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.drop_index(
        "ix_order_shipment_prepare_verified_status",
        table_name="order_shipment_prepare",
    )
    op.drop_index(
        "ix_order_shipment_prepare_parse_hint",
        table_name="order_shipment_prepare",
    )

    with op.batch_alter_table("order_shipment_prepare") as batch_op:
        batch_op.drop_constraint(
            "ck_order_shipment_prepare_parse_hint",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_order_shipment_prepare_verified_status",
            type_="check",
        )
        batch_op.drop_constraint(
            "order_shipment_prepare_verified_by_fkey",
            type_="foreignkey",
        )

        batch_op.drop_column("verified_at")
        batch_op.drop_column("verified_by")
        batch_op.drop_column("address_verified_status")
        batch_op.drop_column("address_parse_hint")


def downgrade() -> None:
    """Downgrade schema."""

    with op.batch_alter_table("order_shipment_prepare") as batch_op:
        batch_op.add_column(
            sa.Column(
                "address_parse_hint",
                sa.String(length=16),
                nullable=False,
                server_default="warning",
                comment="地址解析辅助提示：normal / warning / failed",
            )
        )
        batch_op.add_column(
            sa.Column(
                "address_verified_status",
                sa.String(length=16),
                nullable=False,
                server_default="pending",
                comment="人工核验状态：pending / approved",
            )
        )
        batch_op.add_column(
            sa.Column(
                "verified_by",
                sa.Integer(),
                nullable=True,
                comment="核验通过操作人 users.id",
            )
        )
        batch_op.add_column(
            sa.Column(
                "verified_at",
                sa.DateTime(timezone=True),
                nullable=True,
                comment="核验通过时间",
            )
        )

        batch_op.create_foreign_key(
            "order_shipment_prepare_verified_by_fkey",
            "users",
            ["verified_by"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_check_constraint(
            "ck_order_shipment_prepare_parse_hint",
            "address_parse_hint IN ('normal', 'warning', 'failed')",
        )
        batch_op.create_check_constraint(
            "ck_order_shipment_prepare_verified_status",
            "address_verified_status IN ('pending', 'approved')",
        )

    op.create_index(
        "ix_order_shipment_prepare_parse_hint",
        "order_shipment_prepare",
        ["address_parse_hint"],
        unique=False,
    )
    op.create_index(
        "ix_order_shipment_prepare_verified_status",
        "order_shipment_prepare",
        ["address_verified_status"],
        unique=False,
    )
