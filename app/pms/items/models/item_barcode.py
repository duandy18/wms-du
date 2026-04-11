# app/pms/items/models/item_barcode.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ItemBarcode(Base):
    """
    商品条码表（uom 级绑定终态）

    用途：
    - 绑定条码 → item_id + item_uom_id
    - 包装语义由 item_uom_id 表达（基准单位 / 盒 / 箱 / ...）
    - 码制/来源由 symbology 表达（EAN13 / UPC / GS1 / CUSTOM ...）
    - 主条码用于 UI 显示（itemsStore.primaryBarcodes）
    """

    __tablename__ = "item_barcodes"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    item_uom_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )

    barcode: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    symbology: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'CUSTOM'"),
        comment="条码码制/来源：EAN13 / EAN8 / UPC / UPC12 / GS1 / CUSTOM ...",
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
        ForeignKeyConstraint(
            ["item_uom_id", "item_id"],
            ["item_uoms.id", "item_uoms.item_id"],
            name="fk_item_barcodes_item_uom_pair",
        ),
        Index(
            "uq_item_barcodes_primary",
            "item_id",
            unique=True,
            postgresql_where=text("is_primary = true"),
        ),
        {"info": {"skip_autogen": True}},
    )

    def __repr__(self) -> str:
        return (
            f"<ItemBarcode id={self.id} item={self.item_id} item_uom_id={self.item_uom_id} "
            f"barcode={self.barcode!r} symbology={self.symbology!r} primary={self.is_primary}>"
        )
