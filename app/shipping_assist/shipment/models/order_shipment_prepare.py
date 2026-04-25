# app/shipping_assist/shipment/models/order_shipment_prepare.py
# Domain move: order shipment prepare ORM belongs to TMS shipment.
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrderShipmentPrepare(Base):
    """
    order_shipment_prepare：发运准备阶段总状态表

    职责：
      - address_ready_status：OMS 投影过来的地址就绪状态（pending / ready）
      - package_status：是否已形成包裹方案
      - pricing_status：是否已完成运价计算（订单级汇总状态）
      - provider_status：是否已完成快递公司选择（订单级汇总状态）

    设计要点：
      - 一张订单最多一条准备记录（order_id 主键）
      - 地址事实仍存于 order_address
      - TMS 不负责地址解析 / 地址人工核验 / 地址修改
      - address_ready_status 由 OMS 输入或 OMS 投影同步而来
      - 本表负责“准备阶段汇总状态收口”
      - 包级仓库 / 包级承运商 / 包级报价快照真相在 order_shipment_prepare_packages
      - 本表不负责运输执行事实
    """

    __tablename__ = "order_shipment_prepare"

    order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("orders.id", ondelete="CASCADE"),
        primary_key=True,
    )

    address_ready_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="pending",
        comment="地址就绪状态：pending / ready（来自 OMS）",
    )

    package_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="pending",
        comment="包裹方案状态：pending / planned",
    )

    pricing_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="pending",
        comment="运价计算状态：pending / calculated",
    )

    provider_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="pending",
        comment="快递公司选择状态：pending / selected",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("ix_order_shipment_prepare_address_ready_status", "address_ready_status"),
        Index("ix_order_shipment_prepare_package_status", "package_status"),
        Index("ix_order_shipment_prepare_pricing_status", "pricing_status"),
        Index("ix_order_shipment_prepare_provider_status", "provider_status"),
    )

    def __repr__(self) -> str:
        return (
            "<OrderShipmentPrepare "
            f"order_id={self.order_id} "
            f"address_ready_status={self.address_ready_status} "
            f"package_status={self.package_status} "
            f"pricing_status={self.pricing_status} "
            f"provider_status={self.provider_status}>"
        )
