"""add taobao orders fact tables

Revision ID: ae9d15268b17
Revises: d8403e7d8fe3
Create Date: 2026-03-30 14:33:51.632311

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "ae9d15268b17"
down_revision: Union[str, Sequence[str], None] = "d8403e7d8fe3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "taobao_orders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("store_id", sa.BigInteger(), nullable=False, comment="OMS 店铺 id（stores.id）"),
        sa.Column("tid", sa.String(length=64), nullable=False, comment="淘宝主订单号 tid"),
        sa.Column("status", sa.String(length=64), nullable=True, comment="淘宝原始交易状态"),
        sa.Column("type", sa.String(length=64), nullable=True, comment="淘宝原始交易类型"),
        sa.Column("buyer_nick", sa.String(length=128), nullable=True, comment="买家昵称"),
        sa.Column("buyer_open_uid", sa.String(length=128), nullable=True, comment="买家 OpenUID"),
        sa.Column("receiver_name", sa.String(length=128), nullable=True, comment="收件人姓名"),
        sa.Column("receiver_mobile", sa.String(length=64), nullable=True, comment="收件人手机号"),
        sa.Column("receiver_phone", sa.String(length=64), nullable=True, comment="收件人电话"),
        sa.Column("receiver_state", sa.String(length=64), nullable=True, comment="收件省"),
        sa.Column("receiver_city", sa.String(length=64), nullable=True, comment="收件市"),
        sa.Column("receiver_district", sa.String(length=64), nullable=True, comment="收件区/县"),
        sa.Column("receiver_town", sa.String(length=64), nullable=True, comment="收件街道/镇"),
        sa.Column("receiver_address", sa.String(length=512), nullable=True, comment="收件详细地址"),
        sa.Column("receiver_zip", sa.String(length=32), nullable=True, comment="收件邮编"),
        sa.Column("buyer_memo", sa.Text(), nullable=True, comment="买家备注"),
        sa.Column("buyer_message", sa.Text(), nullable=True, comment="买家留言/附言"),
        sa.Column("seller_memo", sa.Text(), nullable=True, comment="卖家备注"),
        sa.Column("seller_flag", sa.Integer(), nullable=True, comment="卖家备注旗帜"),
        sa.Column("payment", sa.Numeric(precision=14, scale=2), nullable=True, comment="实付金额（元）"),
        sa.Column("total_fee", sa.Numeric(precision=14, scale=2), nullable=True, comment="应付金额（元）"),
        sa.Column("post_fee", sa.Numeric(precision=14, scale=2), nullable=True, comment="邮费（元）"),
        sa.Column("coupon_fee", sa.Numeric(precision=14, scale=2), nullable=True, comment="优惠券金额（元）"),
        sa.Column("created", sa.DateTime(timezone=True), nullable=True, comment="交易创建时间"),
        sa.Column("pay_time", sa.DateTime(timezone=True), nullable=True, comment="付款时间"),
        sa.Column("modified", sa.DateTime(timezone=True), nullable=True, comment="最后修改时间"),
        sa.Column(
            "raw_summary_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="淘宝摘要接口原始 payload",
        ),
        sa.Column(
            "raw_detail_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="淘宝详情接口原始 payload",
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
        sa.UniqueConstraint("store_id", "tid", name="uq_taobao_orders_store_tid"),
    )
    op.create_index("ix_taobao_orders_created", "taobao_orders", ["created"], unique=False)
    op.create_index("ix_taobao_orders_pay_time", "taobao_orders", ["pay_time"], unique=False)
    op.create_index("ix_taobao_orders_status", "taobao_orders", ["status"], unique=False)
    op.create_index("ix_taobao_orders_store_id", "taobao_orders", ["store_id"], unique=False)

    op.create_table(
        "taobao_order_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("taobao_order_id", sa.BigInteger(), nullable=False, comment="所属淘宝订单头 id"),
        sa.Column("tid", sa.String(length=64), nullable=False, comment="淘宝主订单号 tid（冗余保存）"),
        sa.Column("oid", sa.String(length=64), nullable=False, comment="淘宝子订单号 oid"),
        sa.Column("num_iid", sa.String(length=64), nullable=True, comment="商品数字 ID"),
        sa.Column("sku_id", sa.String(length=64), nullable=True, comment="SKU ID"),
        sa.Column("outer_iid", sa.String(length=128), nullable=True, comment="商家外部商品编码"),
        sa.Column("outer_sku_id", sa.String(length=128), nullable=True, comment="商家外部 SKU 编码"),
        sa.Column("title", sa.String(length=255), nullable=True, comment="商品标题"),
        sa.Column("price", sa.Numeric(precision=14, scale=2), nullable=True, comment="单价（元）"),
        sa.Column(
            "num",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="购买数量",
        ),
        sa.Column("payment", sa.Numeric(precision=14, scale=2), nullable=True, comment="子订单实付金额（元）"),
        sa.Column("total_fee", sa.Numeric(precision=14, scale=2), nullable=True, comment="子订单应付金额（元）"),
        sa.Column("sku_properties_name", sa.Text(), nullable=True, comment="SKU 属性名串"),
        sa.Column(
            "raw_item_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="淘宝子订单原始 payload",
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
        sa.ForeignKeyConstraint(["taobao_order_id"], ["taobao_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("taobao_order_id", "oid", name="uq_taobao_order_items_order_oid"),
    )
    op.create_index(
        "ix_taobao_order_items_oid",
        "taobao_order_items",
        ["oid"],
        unique=False,
    )
    op.create_index(
        "ix_taobao_order_items_outer_iid",
        "taobao_order_items",
        ["outer_iid"],
        unique=False,
    )
    op.create_index(
        "ix_taobao_order_items_outer_sku_id",
        "taobao_order_items",
        ["outer_sku_id"],
        unique=False,
    )
    op.create_index(
        "ix_taobao_order_items_taobao_order_id",
        "taobao_order_items",
        ["taobao_order_id"],
        unique=False,
    )
    op.create_index(
        "ix_taobao_order_items_tid",
        "taobao_order_items",
        ["tid"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_taobao_order_items_tid", table_name="taobao_order_items")
    op.drop_index("ix_taobao_order_items_taobao_order_id", table_name="taobao_order_items")
    op.drop_index("ix_taobao_order_items_outer_sku_id", table_name="taobao_order_items")
    op.drop_index("ix_taobao_order_items_outer_iid", table_name="taobao_order_items")
    op.drop_index("ix_taobao_order_items_oid", table_name="taobao_order_items")
    op.drop_table("taobao_order_items")

    op.drop_index("ix_taobao_orders_store_id", table_name="taobao_orders")
    op.drop_index("ix_taobao_orders_status", table_name="taobao_orders")
    op.drop_index("ix_taobao_orders_pay_time", table_name="taobao_orders")
    op.drop_index("ix_taobao_orders_created", table_name="taobao_orders")
    op.drop_table("taobao_orders")
