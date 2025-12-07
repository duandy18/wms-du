# app/models/shipping_record.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ShippingRecord(Base):
    """
    发货记录表 shipping_records

    - 一条记录对应一次发货行为（通常对应一个订单 / 包裹）
    - Phase 2：扩展为“可对账 / 可核算 / 可追踪”的正式账本
    """

    __tablename__ = "shipping_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # 业务引用（通常是 ORD:PDD:1:EXT123）
    order_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    shop_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # 发货仓库（预留，用于“按仓库统计发货成本”）
    warehouse_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 承运商编码（如 ZTO / JT / SF）
    carrier_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # 冗余名称，方便报表展示
    carrier_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # 电子面单 / 运单号
    tracking_no: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # 链路 ID（用于 Trace / Lifecycle 关联）
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # 估算净重（来自订单行 * item.weight_kg，可选）
    weight_kg: Mapped[float | None] = mapped_column(
        Numeric(10, 3),
        nullable=True,
    )
    # 实际称重（毛重）
    gross_weight_kg: Mapped[float | None] = mapped_column(
        Numeric(10, 3),
        nullable=True,
    )
    # 包材重量
    packaging_weight_kg: Mapped[float | None] = mapped_column(
        Numeric(10, 3),
        nullable=True,
    )

    # 预估费用（系统计算）
    cost_estimated: Mapped[float | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )
    # 实际费用（对账后）
    cost_real: Mapped[float | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    # 实际送达时间（可选）
    delivery_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # 状态：IN_TRANSIT / DELIVERED / LOST / RETURNED 等
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # 失败 / 异常信息（比如面单 API 错误码）
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # 额外元数据（自由扩展）
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        Index("ix_shipping_records_ref_time", "order_ref", "created_at"),
        Index("ix_shipping_records_trace_id", "trace_id"),
        Index("ix_shipping_records_tracking_no", "tracking_no"),
    )

    def __repr__(self) -> str:
        return (
            f"<ShippingRecord id={self.id} ref={self.order_ref} "
            f"carrier={self.carrier_code} tracking_no={self.tracking_no} "
            f"warehouse_id={self.warehouse_id} "
            f"trace_id={self.trace_id}>"
        )
