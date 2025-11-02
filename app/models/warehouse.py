# app/models/warehouse.py
from __future__ import annotations

from typing import List

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Warehouse(Base):
    """
    仓库主档（强契约·最小字段集）：
    - id:    主键
    - name:  仓库名称（非空）
    关系：
    - locations: 一对多 -> Location（通过 locations.warehouse_id 外键）
    注意：
    - 当前 batches 表未定义 warehouse_id 外键，故不在本模型声明 batches 关系，避免 NoForeignKeysError。
    """
    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # 只保留“有外键”的关系：locations.warehouse_id -> warehouses.id
    locations: Mapped[List["Location"]] = relationship(
        "Location",
        back_populates="warehouse",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    # ⚠️ 不要在此声明到 Batch 的关系（batches 表当前没有 warehouse_id 外键）
    # batches: Mapped[List["Batch"]] = relationship("Batch", back_populates="warehouse")  # ❌ 禁用

    def __repr__(self) -> str:  # 便于调试与日志
        return f"<Warehouse id={self.id} name={self.name!r}>"
