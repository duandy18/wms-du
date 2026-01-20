# app/models/warehouse.py
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import Boolean, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class WarehouseCode:
    MAIN = "MAIN"
    RETURNS = "RETURNS"
    QUARANTINE = "QUARANTINE"


class Warehouse(Base):
    """
    仓库主档（主数据管理）

    字段约定：
    - id: 自增主键
    - name: 仓库名称（必填，唯一，如“WH-1”／“上海主仓”）
    - code: 仓库编码（可选，唯一，如 WH-SH-01）
    - active: 是否启用（TRUE=可用，FALSE=停用/历史）

    扩展信息：
    - address: 仓库地址（可选）
    - contact_name: 联系人姓名（可选）
    - contact_phone: 联系电话（可选）
    - area_sqm: 仓库面积（平方米，整数，可选）
    """

    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 名称保持原有设置（唯一）
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)

    # 可选编码（唯一）
    code: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        unique=True,
    )

    # 启用状态（下拉过滤、绑定校验都用这个）
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("TRUE"),
    )

    # 扩展信息
    address: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    contact_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    contact_phone: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    area_sqm: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    # 若保留 locations 表，则做弱关系
    locations: Mapped[List["Location"]] = relationship(
        "Location",
        back_populates="warehouse",
        lazy="selectin",
        passive_deletes=True,
    )

    # ✅ Phase 1：仓库 × 快递公司（能力集合 / 事实绑定）
    warehouse_shipping_providers: Mapped[List["WarehouseShippingProvider"]] = relationship(
        "WarehouseShippingProvider",
        back_populates="warehouse",
        lazy="selectin",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Warehouse id={self.id} name={self.name!r}>"
