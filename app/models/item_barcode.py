# app/models/item_barcode.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ItemBarcode(Base):
    """
    商品条码表（v2 完整形态）

    用途：
    - 绑定商品 → barcode → item_id
    - 用于 scan、采购、入库、盘点、出库等全链路
    - 主条码用于 UI 显示（itemsStore.primaryBarcodes）
    """

    __tablename__ = "item_barcodes"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    item_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    barcode: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    kind: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'CUSTOM'"),
        comment="条码类型：EAN13 / UPC / INNER / CUSTOM ...",
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )

    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        # 一个 item 只能有一个主条码（部分索引）
        Index(
            "uq_item_barcodes_primary",
            "item_id",
            unique=True,
            postgresql_where=text("is_primary = true"),
        ),
        # 提示 Alembic 在 autogenerate 时跳过这个表（我们用手写迁移来保证结构）
        {"info": {"skip_autogen": True}},
    )

    def __repr__(self) -> str:
        return (
            f"<ItemBarcode id={self.id} item={self.item_id} "
            f"barcode={self.barcode!r} primary={self.is_primary}>"
        )
