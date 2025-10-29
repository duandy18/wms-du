# app/models/enums.py
from __future__ import annotations
from enum import Enum


# ========= 库存 / 台账移动类型 =========
class MovementType(str, Enum):
    """
    库存移动类型
    - receipt: 入库（Inbound / 调整 +）
    - shipment: 出库（Outbound / 调整 -）
    - transfer: 库位或仓内转移
    - adjustment: 盘盈/盘亏等调整
    """
    RECEIPT = "receipt"
    SHIPMENT = "shipment"
    TRANSFER = "transfer"
    ADJUSTMENT = "adjustment"


# ========= 订单类型 =========
class OrderType(str, Enum):
    """
    订单类型（保持现有取值为大写，兼容既有数据）
    - SALES: 销售订单
    - PURCHASE: 采购订单
    """
    SALES = "SALES"
    PURCHASE = "PURCHASE"


# ========= 订单状态 =========
class OrderStatus(str, Enum):
    """
    订单状态（保持现有取值为大写，兼容既有数据）
    - DRAFT: 草稿
    - CONFIRMED: 已确认（待履约）
    - FULFILLED: 已完成
    - CANCELED: 已取消
    """
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    FULFILLED = "FULFILLED"
    CANCELED = "CANCELED"


__all__ = [
    "MovementType",
    "OrderType",
    "OrderStatus",
]
