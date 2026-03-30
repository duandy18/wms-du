from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from .order import Order
    from .pdd_order import PddOrder


class PddOrderOrderMapping(Base):
    """
    PDD 平台订单 -> 内部业务订单 映射表。

    职责：
    - 保存 pdd_orders 与 orders 的正式桥接关系
    - 作为建单幂等锚点
    - 记录映射来源与当前状态

    第一版按 1:1 设计：
    - 一个 pdd_order 只能对应一个 order
    - 一个 order 只能对应一个 pdd_order
    """

    __tablename__ = "pdd_order_order_mappings"

    __table_args__ = (
        sa.UniqueConstraint(
            "pdd_order_id",
            name="uq_pdd_order_order_mappings_pdd_order_id",
        ),
        sa.UniqueConstraint(
            "order_id",
            name="uq_pdd_order_order_mappings_order_id",
        ),
        sa.Index(
            "ix_pdd_order_order_mappings_mapping_status",
            "mapping_status",
        ),
        sa.Index(
            "ix_pdd_order_order_mappings_mapping_source",
            "mapping_source",
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
        comment="PDD 订单头 id",
    )

    order_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        comment="内部业务订单 id",
    )

    mapping_status: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        server_default=sa.text("'active'"),
        comment="映射状态：active / inactive / replaced / invalid",
    )

    mapping_source: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        server_default=sa.text("'system'"),
        comment="映射来源：system / manual / replay",
    )

    remark: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
        comment="备注",
    )

    created_by: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        nullable=True,
        comment="创建人 user_id（可空）",
    )

    updated_by: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        nullable=True,
        comment="更新人 user_id（可空）",
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

    pdd_order: Mapped["PddOrder"] = relationship(
        "PddOrder",
        back_populates="order_mapping",
        lazy="selectin",
    )

    order: Mapped["Order"] = relationship(
        "Order",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<PddOrderOrderMapping id={self.id} "
            f"pdd_order_id={self.pdd_order_id} order_id={self.order_id} "
            f"status={self.mapping_status} source={self.mapping_source}>"
        )
