"""add pdd order tables and mapping

Revision ID: aa0ebff00956
Revises: 91dc8dc17a4e
Create Date: 2026-03-29 13:47:39.251301

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "aa0ebff00956"
down_revision: Union[str, Sequence[str], None] = "91dc8dc17a4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "pdd_orders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("store_id", sa.BigInteger(), nullable=False, comment="OMS 店铺 id（stores.id）"),
        sa.Column("shop_id", sa.String(length=64), nullable=False, comment="店铺业务 ID（字符串，与 orders.shop_id 语义对齐）"),
        sa.Column("order_sn", sa.String(length=128), nullable=False, comment="PDD 平台订单号"),
        sa.Column("order_status", sa.String(length=32), nullable=True, comment="PDD 原始订单状态"),
        sa.Column("receiver_name", sa.String(length=128), nullable=True, comment="收件人姓名（解密后优先）"),
        sa.Column("receiver_phone", sa.String(length=64), nullable=True, comment="收件人手机号（解密后优先）"),
        sa.Column("receiver_province", sa.String(length=64), nullable=True, comment="收件省"),
        sa.Column("receiver_city", sa.String(length=64), nullable=True, comment="收件市"),
        sa.Column("receiver_district", sa.String(length=64), nullable=True, comment="收件区/县/镇（当前先对齐 town）"),
        sa.Column("receiver_address", sa.String(length=512), nullable=True, comment="详细地址（解密后优先）"),
        sa.Column("buyer_memo", sa.Text(), nullable=True, comment="买家留言"),
        sa.Column("remark", sa.Text(), nullable=True, comment="商家备注 / 平台备注"),
        sa.Column("confirm_at", sa.DateTime(timezone=True), nullable=True, comment="PDD 确认时间（若可取）"),
        sa.Column("goods_amount", sa.Numeric(precision=14, scale=2), nullable=True, comment="货品金额（元）"),
        sa.Column("pay_amount", sa.Numeric(precision=14, scale=2), nullable=True, comment="实付金额（元）"),
        sa.Column("raw_summary_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="PDD 摘要接口原始 payload"),
        sa.Column("raw_detail_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="PDD 详情接口原始 payload"),
        sa.Column(
            "address_check_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending'"),
            comment="地址业务可用性校验状态：pending / passed / failed",
        ),
        sa.Column(
            "item_match_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending'"),
            comment="商品映射状态：pending / matched / partial / failed",
        ),
        sa.Column(
            "admission_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending'"),
            comment="OMS 准入状态：pending / admitted / manual_review / rejected",
        ),
        sa.Column(
            "order_create_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending'"),
            comment="内部订单创建状态：pending / created / manual_review / failed",
        ),
        sa.Column("admission_reason", sa.String(length=255), nullable=True, comment="准入裁决原因摘要"),
        sa.Column("last_error_message", sa.Text(), nullable=True, comment="最近一次失败信息"),
        sa.Column(
            "pulled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="首次拉取入平台表时间",
        ),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="最近一次同步更新时间",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="记录创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="记录更新时间",
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", "order_sn", name="uq_pdd_orders_store_order_sn"),
    )
    op.create_index("ix_pdd_orders_store_id", "pdd_orders", ["store_id"], unique=False)
    op.create_index("ix_pdd_orders_shop_id", "pdd_orders", ["shop_id"], unique=False)
    op.create_index("ix_pdd_orders_order_status", "pdd_orders", ["order_status"], unique=False)
    op.create_index("ix_pdd_orders_admission_status", "pdd_orders", ["admission_status"], unique=False)
    op.create_index("ix_pdd_orders_order_create_status", "pdd_orders", ["order_create_status"], unique=False)

    op.create_table(
        "pdd_order_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("pdd_order_id", sa.BigInteger(), nullable=False, comment="所属 PDD 订单头 id"),
        sa.Column("order_sn", sa.String(length=128), nullable=False, comment="PDD 平台订单号（冗余保存，便于查询）"),
        sa.Column("platform_goods_id", sa.String(length=64), nullable=True, comment="PDD goods_id"),
        sa.Column("platform_sku_id", sa.String(length=64), nullable=True, comment="PDD sku_id"),
        sa.Column("outer_id", sa.String(length=128), nullable=True, comment="PDD outer_id / 商家编码"),
        sa.Column("sku_code", sa.String(length=128), nullable=True, comment="归一后的 sku_code（通常来自 outer_id）"),
        sa.Column("goods_name", sa.String(length=255), nullable=True, comment="平台商品名"),
        sa.Column("sku_name", sa.String(length=255), nullable=True, comment="平台规格名"),
        sa.Column(
            "goods_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="购买数量",
        ),
        sa.Column("goods_price", sa.Numeric(precision=14, scale=2), nullable=True, comment="单价（元）"),
        sa.Column("line_amount", sa.Numeric(precision=14, scale=2), nullable=True, comment="行金额（元）"),
        sa.Column("raw_item_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="PDD 行原始 payload"),
        sa.Column(
            "match_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending'"),
            comment="商品匹配状态：pending / matched / multiple_candidates / not_found / invalid_code",
        ),
        sa.Column("match_reason", sa.String(length=255), nullable=True, comment="商品匹配结果原因摘要"),
        sa.Column("matched_item_id", sa.Integer(), nullable=True, comment="匹配到的内部 item_id"),
        sa.Column("matched_fsku_id", sa.BigInteger(), nullable=True, comment="匹配到的内部 fsku_id"),
        sa.Column(
            "matched_binding_id",
            sa.BigInteger(),
            nullable=True,
            comment="命中的 merchant_code_fsku_binding id",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="记录创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="记录更新时间",
        ),
        sa.ForeignKeyConstraint(["matched_binding_id"], ["merchant_code_fsku_bindings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["matched_fsku_id"], ["fskus.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["matched_item_id"], ["items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["pdd_order_id"], ["pdd_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pdd_order_items_pdd_order_id", "pdd_order_items", ["pdd_order_id"], unique=False)
    op.create_index("ix_pdd_order_items_order_sn", "pdd_order_items", ["order_sn"], unique=False)
    op.create_index("ix_pdd_order_items_outer_id", "pdd_order_items", ["outer_id"], unique=False)
    op.create_index("ix_pdd_order_items_sku_code", "pdd_order_items", ["sku_code"], unique=False)
    op.create_index("ix_pdd_order_items_match_status", "pdd_order_items", ["match_status"], unique=False)

    op.create_table(
        "pdd_order_order_mappings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("pdd_order_id", sa.BigInteger(), nullable=False, comment="PDD 订单头 id"),
        sa.Column("order_id", sa.BigInteger(), nullable=False, comment="内部业务订单 id"),
        sa.Column(
            "mapping_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'active'"),
            comment="映射状态：active / inactive / replaced / invalid",
        ),
        sa.Column(
            "mapping_source",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'system'"),
            comment="映射来源：system / manual / replay",
        ),
        sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        sa.Column("created_by", sa.BigInteger(), nullable=True, comment="创建人 user_id（可空）"),
        sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="更新人 user_id（可空）"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="记录创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="记录更新时间",
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pdd_order_id"], ["pdd_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uq_pdd_order_order_mappings_order_id"),
        sa.UniqueConstraint("pdd_order_id", name="uq_pdd_order_order_mappings_pdd_order_id"),
    )
    op.create_index(
        "ix_pdd_order_order_mappings_mapping_status",
        "pdd_order_order_mappings",
        ["mapping_status"],
        unique=False,
    )
    op.create_index(
        "ix_pdd_order_order_mappings_mapping_source",
        "pdd_order_order_mappings",
        ["mapping_source"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index("ix_pdd_order_order_mappings_mapping_source", table_name="pdd_order_order_mappings")
    op.drop_index("ix_pdd_order_order_mappings_mapping_status", table_name="pdd_order_order_mappings")
    op.drop_table("pdd_order_order_mappings")

    op.drop_index("ix_pdd_order_items_match_status", table_name="pdd_order_items")
    op.drop_index("ix_pdd_order_items_sku_code", table_name="pdd_order_items")
    op.drop_index("ix_pdd_order_items_outer_id", table_name="pdd_order_items")
    op.drop_index("ix_pdd_order_items_order_sn", table_name="pdd_order_items")
    op.drop_index("ix_pdd_order_items_pdd_order_id", table_name="pdd_order_items")
    op.drop_table("pdd_order_items")

    op.drop_index("ix_pdd_orders_order_create_status", table_name="pdd_orders")
    op.drop_index("ix_pdd_orders_admission_status", table_name="pdd_orders")
    op.drop_index("ix_pdd_orders_order_status", table_name="pdd_orders")
    op.drop_index("ix_pdd_orders_shop_id", table_name="pdd_orders")
    op.drop_index("ix_pdd_orders_store_id", table_name="pdd_orders")
    op.drop_table("pdd_orders")
