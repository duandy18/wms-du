# app/schemas/order_item.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    """
    通用基类：
    - from_attributes: 支持 SQLAlchemy ORM 自动序列化；
    - extra = ignore: 忽略旧字段 / 未映射字段；
    - populate_by_name: 允许通过字段名或别名填充。
    """

    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


class OrderItemRow(_Base):
    """
    订单行（order_items）标准出参模型：

    对应字段：
      - id          : order_items.id
      - order_id    : order_items.order_id
      - item_id     : order_items.item_id
      - sku_id      : order_items.sku_id
      - title       : order_items.title
      - qty         : order_items.qty
      - price       : order_items.price
      - discount    : order_items.discount
      - amount      : order_items.amount
      - extras      : order_items.extras（JSONB）
    """

    id: int = Field(..., description="订单行 ID（order_items.id）")
    order_id: int = Field(..., description="所属订单 ID（orders.id）")
    item_id: int = Field(..., description="内部商品 ID（items.id）")

    sku_id: Optional[str] = Field(
        default=None,
        description="平台 SKU / 规格 ID（order_items.sku_id）",
    )

    title: Optional[str] = Field(
        default=None,
        description="商品标题快照（order_items.title）",
    )

    qty: Optional[int] = Field(
        default=None,
        description="下单数量（order_items.qty）",
    )

    price: Optional[Decimal] = Field(
        default=None,
        description="行单价（order_items.price）",
    )

    discount: Optional[Decimal] = Field(
        default=None,
        description="行折扣金额（order_items.discount）",
    )

    amount: Optional[Decimal] = Field(
        default=None,
        description="行金额（order_items.amount）",
    )

    extras: Optional[Dict[str, Any]] = Field(
        default=None,
        description="行级附加 JSON（order_items.extras）",
    )


__all__ = ["OrderItemRow"]
