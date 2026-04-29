# app/pms/items/models/item_sku_code.py
from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.pms.items.models.item import Item


class ItemSkuCodeType(str, enum.Enum):
    PRIMARY = "PRIMARY"
    ALIAS = "ALIAS"
    LEGACY = "LEGACY"
    MANUAL = "MANUAL"


class ItemSkuCode(Base):
    """
    商品 SKU 多编码治理表。

    设计原则：
    - item_id 是商品内部身份真相；
    - items.sku 是当前主 SKU 投影；
    - item_sku_codes 是商品编码治理真相表；
    - 历史采购 / 入库 / 财务单据里的 item_sku 是当时展示快照，不追改。
    """

    __tablename__ = "item_sku_codes"

    __table_args__ = (
        sa.UniqueConstraint("code", name="uq_item_sku_codes_code"),
        sa.Index(
            "uq_item_sku_codes_one_primary_per_item",
            "item_id",
            unique=True,
            postgresql_where=sa.text("is_primary = true"),
        ),
        sa.CheckConstraint("length(trim(code)) > 0", name="ck_item_sku_codes_code_non_empty"),
        sa.CheckConstraint(
            "code_type in ('PRIMARY', 'ALIAS', 'LEGACY', 'MANUAL')",
            name="ck_item_sku_codes_code_type",
        ),
        sa.CheckConstraint(
            "(is_primary = false) OR (is_active = true)",
            name="ck_item_sku_codes_primary_active",
        ),
        sa.CheckConstraint(
            "(is_primary = false) OR (effective_to IS NULL)",
            name="ck_item_sku_codes_primary_no_effective_to",
        ),
        sa.CheckConstraint(
            "((code_type = 'PRIMARY') = (is_primary = true))",
            name="ck_item_sku_codes_primary_type_matches_flag",
        ),
    )

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)

    item_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("items.id", name="fk_item_sku_codes_item", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    code: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    code_type: Mapped[str] = mapped_column(sa.String(16), nullable=False)

    is_primary: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("true"))

    effective_from: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    remark: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )

    item: Mapped["Item"] = relationship("Item", back_populates="sku_codes")

    def __repr__(self) -> str:
        return (
            f"<ItemSkuCode id={self.id} item_id={self.item_id} "
            f"code={self.code!r} code_type={self.code_type!r} "
            f"is_primary={self.is_primary} is_active={self.is_active}>"
        )
