# app/models/shipping_record.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, BigInteger, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ShippingRecord(Base):
    """
    物流台帐表 shipping_records

    语义定位：

    - 一条记录代表一次“仓库交付物流”的发货台帐
    - 只记录发货事实，不承担物流状态、不承担对账结果
    - 对账结果存储在 shipping_record_reconciliations 表
    """

    __tablename__ = "shipping_records"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    # 订单引用
    order_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    shop_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # 发货仓库
    warehouse_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # 承运网点
    shipping_provider_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_providers.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # 冗余展示字段
    carrier_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    carrier_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # 运单号
    tracking_no: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # 包裹总重量
    gross_weight_kg: Mapped[float | None] = mapped_column(
        Numeric(10, 3),
        nullable=True,
    )

    # 费用拆分
    freight_estimated: Mapped[float | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )
    surcharge_estimated: Mapped[float | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    # 系统预估总费用（总额）
    cost_estimated: Mapped[float | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    # 包裹尺寸（厘米）
    length_cm: Mapped[float | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    width_cm: Mapped[float | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    height_cm: Mapped[float | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    # 寄件人
    sender: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    # 目的地
    dest_province: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dest_city: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        Index("ix_shipping_records_ref_time", "order_ref", "created_at"),
        Index("ix_shipping_records_tracking_no", "tracking_no"),
        Index("ix_shipping_records_provider_id", "shipping_provider_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<ShippingRecord id={self.id} "
            f"ref={self.order_ref} "
            f"tracking_no={self.tracking_no} "
            f"warehouse_id={self.warehouse_id} "
            f"provider_id={self.shipping_provider_id}>"
        )
