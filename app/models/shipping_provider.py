# app/models/shipping_provider.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ShippingProvider(Base):
    """
    物流/快递公司主数据（Phase 1）

    字段与 suppliers 基本对齐：
    - name         : 公司名称（必填，唯一）
    - code         : 编码（可选，唯一，如 SF / ZTO）
    - contact_name : 联系人姓名
    - phone        : 联系电话
    - email        : 电子邮件
    - wechat       : 微信号
    - active       : 是否启用

    新字段（用于 Ship）：
    - priority      : 排序优先级（数值越小优先级越高）
    - pricing_model : 计费模型 JSON（by_weight 等）
    - region_rules  : 区域覆盖 JSON（按省份覆盖 base_cost 等）
    """

    __tablename__ = "shipping_providers"
    __table_args__ = (
        UniqueConstraint("name", name="uq_shipping_providers_name"),
        UniqueConstraint("code", name="uq_shipping_providers_code"),
        {"info": {"skip_autogen": True}},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    contact_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    wechat: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="TRUE",
    )

    # Ship 相关字段
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, server_default="100"
    )
    pricing_model: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    region_rules: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

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

    def __repr__(self) -> str:
        return (
            f"<ShippingProvider id={self.id} name={self.name!r} "
            f"active={self.active} priority={self.priority}>"
        )
