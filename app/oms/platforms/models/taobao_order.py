# app/oms/platforms/models/taobao_order.py
# Domain move: Taobao order fact ORM belongs to OMS platform order ledger.
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TaobaoOrder(Base):
    """
    淘宝平台订单头事实表（taobao_orders）。

    职责：
    - 保存淘宝平台订单头原生事实字段
    - 保存收件信息快照
    - 保存淘宝摘要 / 详情原始 payload

    不负责：
    - 保存内部桥接 / 匹配 / 准入 / 建单状态
    - 替代内部 orders 主表
    """

    __tablename__ = "taobao_orders"

    __table_args__ = (
        sa.UniqueConstraint(
            "store_id",
            "tid",
            name="uq_taobao_orders_store_tid",
        ),
        sa.Index(
            "ix_taobao_orders_store_id",
            "store_id",
        ),
        sa.Index(
            "ix_taobao_orders_status",
            "status",
        ),
        sa.Index(
            "ix_taobao_orders_created",
            "created",
        ),
        sa.Index(
            "ix_taobao_orders_pay_time",
            "pay_time",
        ),
    )

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    store_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        comment="OMS 店铺 id（stores.id）",
    )

    tid: Mapped[str] = mapped_column(
        sa.String(64),
        nullable=False,
        comment="淘宝主订单号 tid",
    )

    status: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        comment="淘宝原始交易状态",
    )

    type: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        comment="淘宝原始交易类型",
    )

    buyer_nick: Mapped[str | None] = mapped_column(
        sa.String(128),
        nullable=True,
        comment="买家昵称",
    )

    buyer_open_uid: Mapped[str | None] = mapped_column(
        sa.String(128),
        nullable=True,
        comment="买家 OpenUID",
    )

    receiver_name: Mapped[str | None] = mapped_column(
        sa.String(128),
        nullable=True,
        comment="收件人姓名",
    )

    receiver_mobile: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        comment="收件人手机号",
    )

    receiver_phone: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        comment="收件人电话",
    )

    receiver_state: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        comment="收件省",
    )

    receiver_city: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        comment="收件市",
    )

    receiver_district: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        comment="收件区/县",
    )

    receiver_town: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        comment="收件街道/镇",
    )

    receiver_address: Mapped[str | None] = mapped_column(
        sa.String(512),
        nullable=True,
        comment="收件详细地址",
    )

    receiver_zip: Mapped[str | None] = mapped_column(
        sa.String(32),
        nullable=True,
        comment="收件邮编",
    )

    buyer_memo: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
        comment="买家备注",
    )

    buyer_message: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
        comment="买家留言/附言",
    )

    seller_memo: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
        comment="卖家备注",
    )

    seller_flag: Mapped[int | None] = mapped_column(
        sa.Integer,
        nullable=True,
        comment="卖家备注旗帜",
    )

    payment: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(14, 2),
        nullable=True,
        comment="实付金额（元）",
    )

    total_fee: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(14, 2),
        nullable=True,
        comment="应付金额（元）",
    )

    post_fee: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(14, 2),
        nullable=True,
        comment="邮费（元）",
    )

    coupon_fee: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(14, 2),
        nullable=True,
        comment="优惠券金额（元）",
    )

    created: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        comment="交易创建时间",
    )

    pay_time: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        comment="付款时间",
    )

    modified: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        comment="最后修改时间",
    )

    raw_summary_payload: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="淘宝摘要接口原始 payload",
    )

    raw_detail_payload: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="淘宝详情接口原始 payload",
    )

    pulled_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        comment="首次拉取入平台表时间",
    )

    last_synced_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        comment="最近一次同步更新时间",
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        comment="记录创建时间",
    )

    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        comment="记录更新时间",
    )

    items: Mapped[List["TaobaoOrderItem"]] = relationship(
        "TaobaoOrderItem",
        back_populates="order",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<TaobaoOrder id={self.id} store_id={self.store_id} "
            f"tid={self.tid} status={self.status}>"
        )


class TaobaoOrderItem(Base):
    """
    淘宝平台子订单事实表（taobao_order_items）。

    职责：
    - 保存淘宝子订单原生商品行字段
    - 保存子订单原始 payload
    """

    __tablename__ = "taobao_order_items"

    __table_args__ = (
        sa.UniqueConstraint(
            "taobao_order_id",
            "oid",
            name="uq_taobao_order_items_order_oid",
        ),
        sa.Index(
            "ix_taobao_order_items_taobao_order_id",
            "taobao_order_id",
        ),
        sa.Index(
            "ix_taobao_order_items_tid",
            "tid",
        ),
        sa.Index(
            "ix_taobao_order_items_oid",
            "oid",
        ),
        sa.Index(
            "ix_taobao_order_items_outer_iid",
            "outer_iid",
        ),
        sa.Index(
            "ix_taobao_order_items_outer_sku_id",
            "outer_sku_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    taobao_order_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("taobao_orders.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属淘宝订单头 id",
    )

    tid: Mapped[str] = mapped_column(
        sa.String(64),
        nullable=False,
        comment="淘宝主订单号 tid（冗余保存）",
    )

    oid: Mapped[str] = mapped_column(
        sa.String(64),
        nullable=False,
        comment="淘宝子订单号 oid",
    )

    num_iid: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        comment="商品数字 ID",
    )

    sku_id: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        comment="SKU ID",
    )

    outer_iid: Mapped[str | None] = mapped_column(
        sa.String(128),
        nullable=True,
        comment="商家外部商品编码",
    )

    outer_sku_id: Mapped[str | None] = mapped_column(
        sa.String(128),
        nullable=True,
        comment="商家外部 SKU 编码",
    )

    title: Mapped[str | None] = mapped_column(
        sa.String(255),
        nullable=True,
        comment="商品标题",
    )

    price: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(14, 2),
        nullable=True,
        comment="单价（元）",
    )

    num: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default="0",
        comment="购买数量",
    )

    payment: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(14, 2),
        nullable=True,
        comment="子订单实付金额（元）",
    )

    total_fee: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(14, 2),
        nullable=True,
        comment="子订单应付金额（元）",
    )

    sku_properties_name: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
        comment="SKU 属性名串",
    )

    raw_item_payload: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="淘宝子订单原始 payload",
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        comment="记录创建时间",
    )

    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        comment="记录更新时间",
    )

    order: Mapped["TaobaoOrder"] = relationship(
        "TaobaoOrder",
        back_populates="items",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<TaobaoOrderItem id={self.id} taobao_order_id={self.taobao_order_id} "
            f"oid={self.oid} qty={self.num}>"
        )
