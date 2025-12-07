from __future__ import annotations

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Inventory(Base):
    """
    旧版“库存流水/变更”模型（如仍在用）。
    注意：避免使用属性名 metadata（Declarative 保留）。
    """

    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    location_id: Mapped[int | None] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    ref: Mapped[str | None] = mapped_column(String(255))
    # DB 列名仍为 "metadata"，Python 侧改名为 meta_json
    meta_json: Mapped[dict | None] = mapped_column("metadata", JSON)
    occurred_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
