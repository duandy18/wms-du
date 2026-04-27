# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
# app/platform_order_ingestion/models/pdd_order.py
# Domain move: PDD order fact ORM belongs to OMS platform order ledger.
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base



class PddOrder(Base):
    """
    拼多多平台订单头表（pdd_orders）。

    职责：
    - 保存 PDD 平台订单头事实
    - 保存解密后的收件信息快照
    - 保存 PDD 原始 payload

    不负责：
    - 直接承载内部业务订单执行语义
    - 直接替代 orders
    - 直接保存 OMS 后续桥接 / 准入 / 建单状态
    """

    __tablename__ = "pdd_orders"

    __table_args__ = (
        sa.UniqueConstraint(
            "store_id",
            "order_sn",
            name="uq_pdd_orders_store_order_sn",
        ),
        sa.Index(
            "ix_pdd_orders_store_id",
            "store_id",
        ),
        sa.Index(
            "ix_pdd_orders_order_status",
            "order_status",
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

    order_sn: Mapped[str] = mapped_column(
        sa.String(128),
        nullable=False,
        comment="PDD 平台订单号",
    )

    order_status: Mapped[str | None] = mapped_column(
        sa.String(32),
        nullable=True,
        comment="PDD 原始订单状态",
    )

    receiver_name: Mapped[str | None] = mapped_column(
        sa.String(128),
        nullable=True,
        comment="收件人姓名（解密后优先）",
    )

    receiver_phone: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        comment="收件人手机号（解密后优先）",
    )

    receiver_province: Mapped[str | None] = mapped_column(
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
        comment="收件区/县/镇（当前先对齐 town）",
    )

    receiver_address: Mapped[str | None] = mapped_column(
        sa.String(512),
        nullable=True,
        comment="详细地址（解密后优先）",
    )

    buyer_memo: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
        comment="买家留言",
    )

    remark: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
        comment="商家备注 / 平台备注",
    )

    confirm_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        comment="PDD 确认时间（若可取）",
    )

    goods_amount: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(14, 2),
        nullable=True,
        comment="货品金额（元）",
    )

    pay_amount: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(14, 2),
        nullable=True,
        comment="实付金额（元）",
    )

    raw_summary_payload: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="PDD 摘要接口原始 payload",
    )

    raw_detail_payload: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="PDD 详情接口原始 payload",
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

    items: Mapped[List["PddOrderItem"]] = relationship(
        "PddOrderItem",
        back_populates="order",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


    def __repr__(self) -> str:
        return (
            f"<PddOrder id={self.id} store_id={self.store_id} "
            f"order_sn={self.order_sn} status={self.order_status}>"
        )


class PddOrderItem(Base):
    """
    拼多多平台订单行表（pdd_order_items）。

    职责：
    - 保存 PDD 平台原始商品行
    - 只保存平台原生商品标识与原始 payload
    """

    __tablename__ = "pdd_order_items"

    __table_args__ = (
        sa.Index(
            "ix_pdd_order_items_pdd_order_id",
            "pdd_order_id",
        ),
        sa.Index(
            "ix_pdd_order_items_order_sn",
            "order_sn",
        ),
        sa.Index(
            "ix_pdd_order_items_outer_id",
            "outer_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    pdd_order_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("pdd_orders.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属 PDD 订单头 id",
    )

    order_sn: Mapped[str] = mapped_column(
        sa.String(128),
        nullable=False,
        comment="PDD 平台订单号（冗余保存，便于查询）",
    )

    platform_goods_id: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        comment="PDD goods_id",
    )

    platform_sku_id: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        comment="PDD sku_id",
    )

    outer_id: Mapped[str | None] = mapped_column(
        sa.String(128),
        nullable=True,
        comment="PDD outer_id / 商家编码",
    )

    goods_name: Mapped[str | None] = mapped_column(
        sa.String(255),
        nullable=True,
        comment="平台商品名",
    )

    goods_count: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default="0",
        comment="购买数量",
    )

    goods_price: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(14, 2),
        nullable=True,
        comment="单价（元）",
    )

    raw_item_payload: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="PDD 行原始 payload",
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

    order: Mapped["PddOrder"] = relationship(
        "PddOrder",
        back_populates="items",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<PddOrderItem id={self.id} pdd_order_id={self.pdd_order_id} "
            f"outer_id={self.outer_id} qty={self.goods_count}>"
        )
