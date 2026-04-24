# app/oms/platforms/models/jd_order.py
# Domain move: JD order fact ORM belongs to OMS platform order ledger.
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class JdOrder(Base):
    """
    京东平台订单头事实表（jd_orders）。

    职责：
    - 保存 JD 平台订单头原生事实字段
    - 保存收件信息快照
    - 保存 JD 摘要 / 详情原始 payload

    不负责：
    - 保存内部桥接 / 匹配 / 准入 / 建单状态
    - 替代内部 orders 主表
    """

    __tablename__ = "jd_orders"

    __table_args__ = (
        sa.UniqueConstraint(
            "store_id",
            "order_id",
            name="uq_jd_orders_store_order_id",
        ),
        sa.Index(
            "ix_jd_orders_store_id",
            "store_id",
        ),
        sa.Index(
            "ix_jd_orders_order_state",
            "order_state",
        ),
        sa.Index(
            "ix_jd_orders_order_start_time",
            "order_start_time",
        ),
        sa.Index(
            "ix_jd_orders_modified",
            "modified",
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

    order_id: Mapped[str] = mapped_column(
        sa.String(64),
        nullable=False,
        comment="京东主订单号 order_id",
    )

    vender_id: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        comment="京东商家 id / vender_id",
    )

    order_type: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        comment="京东原始订单类型",
    )

    order_state: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        comment="京东原始订单状态",
    )

    buyer_pin: Mapped[str | None] = mapped_column(
        sa.String(128),
        nullable=True,
        comment="买家标识 buyer_pin",
    )

    consignee_name: Mapped[str | None] = mapped_column(
        sa.String(128),
        nullable=True,
        comment="收件人姓名",
    )

    consignee_mobile: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        comment="收件人手机号",
    )

    consignee_phone: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        comment="收件人电话",
    )

    consignee_province: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        comment="收件省",
    )

    consignee_city: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        comment="收件市",
    )

    consignee_county: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        comment="收件区/县",
    )

    consignee_town: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        comment="收件街道/镇",
    )

    consignee_address: Mapped[str | None] = mapped_column(
        sa.String(512),
        nullable=True,
        comment="收件详细地址",
    )

    order_remark: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
        comment="订单备注 / 买家备注",
    )

    seller_remark: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
        comment="卖家备注",
    )

    order_total_price: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(14, 2),
        nullable=True,
        comment="订单总金额（元）",
    )

    order_seller_price: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(14, 2),
        nullable=True,
        comment="商家应收金额（元）",
    )

    freight_price: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(14, 2),
        nullable=True,
        comment="运费金额（元）",
    )

    payment_confirm: Mapped[str | None] = mapped_column(
        sa.String(32),
        nullable=True,
        comment="付款确认状态",
    )

    order_start_time: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        comment="下单时间 / 订单开始时间",
    )

    order_end_time: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        comment="订单结束时间",
    )

    modified: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        comment="最后修改时间",
    )

    raw_summary_payload: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="JD 摘要接口原始 payload",
    )

    raw_detail_payload: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="JD 详情接口原始 payload",
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

    items: Mapped[List["JdOrderItem"]] = relationship(
        "JdOrderItem",
        back_populates="order",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<JdOrder id={self.id} store_id={self.store_id} "
            f"order_id={self.order_id} state={self.order_state}>"
        )


class JdOrderItem(Base):
    """
    京东平台订单行事实表（jd_order_items）。

    职责：
    - 保存 JD 平台原始商品行字段
    - 保存 JD 订单行原始 payload
    """

    __tablename__ = "jd_order_items"

    __table_args__ = (
        sa.UniqueConstraint(
            "jd_order_id",
            "sku_id",
            "ware_id",
            name="uq_jd_order_items_order_sku_ware",
        ),
        sa.Index(
            "ix_jd_order_items_jd_order_id",
            "jd_order_id",
        ),
        sa.Index(
            "ix_jd_order_items_order_id",
            "order_id",
        ),
        sa.Index(
            "ix_jd_order_items_outer_sku_id",
            "outer_sku_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    jd_order_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("jd_orders.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属 JD 订单头 id",
    )

    order_id: Mapped[str] = mapped_column(
        sa.String(64),
        nullable=False,
        comment="京东主订单号（冗余保存）",
    )

    sku_id: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        comment="京东 sku_id",
    )

    outer_sku_id: Mapped[str | None] = mapped_column(
        sa.String(128),
        nullable=True,
        comment="商家外部 SKU 编码",
    )

    ware_id: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        comment="京东商品 ware_id",
    )

    item_name: Mapped[str | None] = mapped_column(
        sa.String(255),
        nullable=True,
        comment="商品名称",
    )

    item_total: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default="0",
        comment="购买数量",
    )

    item_price: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(14, 2),
        nullable=True,
        comment="单价（元）",
    )

    sku_name: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
        comment="SKU 规格描述",
    )

    gift_point: Mapped[int | None] = mapped_column(
        sa.Integer,
        nullable=True,
        comment="是否赠品标识 / gift_point",
    )

    raw_item_payload: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="JD 行原始 payload",
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

    order: Mapped["JdOrder"] = relationship(
        "JdOrder",
        back_populates="items",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<JdOrderItem id={self.id} jd_order_id={self.jd_order_id} "
            f"sku_id={self.sku_id} qty={self.item_total}>"
        )
