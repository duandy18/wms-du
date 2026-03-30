"""add_jd_orders

Revision ID: 708d983562de
Revises: aff2e0913304
Create Date: 2026-03-30 17:38:03.812032

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "708d983562de"
down_revision: Union[str, Sequence[str], None] = "aff2e0913304"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "jd_orders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("store_id", sa.BigInteger(), nullable=False, comment="OMS 店铺 id（stores.id）"),
        sa.Column("order_id", sa.String(length=64), nullable=False, comment="京东主订单号 order_id"),
        sa.Column("vender_id", sa.String(length=64), nullable=True, comment="京东商家 id / vender_id"),
        sa.Column("order_type", sa.String(length=64), nullable=True, comment="京东原始订单类型"),
        sa.Column("order_state", sa.String(length=64), nullable=True, comment="京东原始订单状态"),
        sa.Column("buyer_pin", sa.String(length=128), nullable=True, comment="买家标识 buyer_pin"),
        sa.Column("consignee_name", sa.String(length=128), nullable=True, comment="收件人姓名"),
        sa.Column("consignee_mobile", sa.String(length=64), nullable=True, comment="收件人手机号"),
        sa.Column("consignee_phone", sa.String(length=64), nullable=True, comment="收件人电话"),
        sa.Column("consignee_province", sa.String(length=64), nullable=True, comment="收件省"),
        sa.Column("consignee_city", sa.String(length=64), nullable=True, comment="收件市"),
        sa.Column("consignee_county", sa.String(length=64), nullable=True, comment="收件区/县"),
        sa.Column("consignee_town", sa.String(length=64), nullable=True, comment="收件街道/镇"),
        sa.Column("consignee_address", sa.String(length=512), nullable=True, comment="收件详细地址"),
        sa.Column("order_remark", sa.Text(), nullable=True, comment="订单备注 / 买家备注"),
        sa.Column("seller_remark", sa.Text(), nullable=True, comment="卖家备注"),
        sa.Column("order_total_price", sa.Numeric(precision=14, scale=2), nullable=True, comment="订单总金额（元）"),
        sa.Column("order_seller_price", sa.Numeric(precision=14, scale=2), nullable=True, comment="商家应收金额（元）"),
        sa.Column("freight_price", sa.Numeric(precision=14, scale=2), nullable=True, comment="运费金额（元）"),
        sa.Column("payment_confirm", sa.String(length=32), nullable=True, comment="付款确认状态"),
        sa.Column("order_start_time", sa.DateTime(timezone=True), nullable=True, comment="下单时间 / 订单开始时间"),
        sa.Column("order_end_time", sa.DateTime(timezone=True), nullable=True, comment="订单结束时间"),
        sa.Column("modified", sa.DateTime(timezone=True), nullable=True, comment="最后修改时间"),
        sa.Column(
            "raw_summary_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="JD 摘要接口原始 payload",
        ),
        sa.Column(
            "raw_detail_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="JD 详情接口原始 payload",
        ),
        sa.Column(
            "pulled_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="首次拉取入平台表时间",
        ),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="最近一次同步更新时间",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="记录创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="记录更新时间",
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", "order_id", name="uq_jd_orders_store_order_id"),
    )
    op.create_index("ix_jd_orders_store_id", "jd_orders", ["store_id"], unique=False)
    op.create_index("ix_jd_orders_order_state", "jd_orders", ["order_state"], unique=False)
    op.create_index(
        "ix_jd_orders_order_start_time",
        "jd_orders",
        ["order_start_time"],
        unique=False,
    )
    op.create_index("ix_jd_orders_modified", "jd_orders", ["modified"], unique=False)

    op.create_table(
        "jd_order_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("jd_order_id", sa.BigInteger(), nullable=False, comment="所属 JD 订单头 id"),
        sa.Column("order_id", sa.String(length=64), nullable=False, comment="京东主订单号（冗余保存）"),
        sa.Column("sku_id", sa.String(length=64), nullable=True, comment="京东 sku_id"),
        sa.Column("outer_sku_id", sa.String(length=128), nullable=True, comment="商家外部 SKU 编码"),
        sa.Column("ware_id", sa.String(length=64), nullable=True, comment="京东商品 ware_id"),
        sa.Column("item_name", sa.String(length=255), nullable=True, comment="商品名称"),
        sa.Column("item_total", sa.Integer(), server_default="0", nullable=False, comment="购买数量"),
        sa.Column("item_price", sa.Numeric(precision=14, scale=2), nullable=True, comment="单价（元）"),
        sa.Column("sku_name", sa.Text(), nullable=True, comment="SKU 规格描述"),
        sa.Column("gift_point", sa.Integer(), nullable=True, comment="是否赠品标识 / gift_point"),
        sa.Column(
            "raw_item_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="JD 行原始 payload",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="记录创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="记录更新时间",
        ),
        sa.ForeignKeyConstraint(["jd_order_id"], ["jd_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "jd_order_id",
            "sku_id",
            "ware_id",
            name="uq_jd_order_items_order_sku_ware",
        ),
    )
    op.create_index(
        "ix_jd_order_items_jd_order_id",
        "jd_order_items",
        ["jd_order_id"],
        unique=False,
    )
    op.create_index(
        "ix_jd_order_items_order_id",
        "jd_order_items",
        ["order_id"],
        unique=False,
    )
    op.create_index(
        "ix_jd_order_items_outer_sku_id",
        "jd_order_items",
        ["outer_sku_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_jd_order_items_outer_sku_id", table_name="jd_order_items")
    op.drop_index("ix_jd_order_items_order_id", table_name="jd_order_items")
    op.drop_index("ix_jd_order_items_jd_order_id", table_name="jd_order_items")
    op.drop_table("jd_order_items")

    op.drop_index("ix_jd_orders_modified", table_name="jd_orders")
    op.drop_index("ix_jd_orders_order_start_time", table_name="jd_orders")
    op.drop_index("ix_jd_orders_order_state", table_name="jd_orders")
    op.drop_index("ix_jd_orders_store_id", table_name="jd_orders")
    op.drop_table("jd_orders")
