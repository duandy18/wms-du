# app/models/enums/ledger_enums.py
from __future__ import annotations

from enum import Enum


class ReasonCanon(str, Enum):
    """
    台账稳定口径（冻结合同）：
    - RECEIPT    入库
    - SHIPMENT   出库
    - ADJUSTMENT 调整/盘点
    """

    RECEIPT = "RECEIPT"
    SHIPMENT = "SHIPMENT"
    ADJUSTMENT = "ADJUSTMENT"


class SubReason(str, Enum):
    """
    台账具体动作（冻结合同）

    入库：
    - PO_RECEIPT         采购入库
    - RETURN_RECEIPT     退货入库

    出库：
    - ORDER_SHIP         订单出库
    - INTERNAL_SHIP      内部出库
    - RETURN_TO_VENDOR   退供应商出库

    调整：
    - COUNT_ADJUST       盘点确认（允许 delta=0 的确认事件）
    """

    # 入库
    PO_RECEIPT = "PO_RECEIPT"
    RETURN_RECEIPT = "RETURN_RECEIPT"

    # 出库
    ORDER_SHIP = "ORDER_SHIP"
    INTERNAL_SHIP = "INTERNAL_SHIP"
    RETURN_TO_VENDOR = "RETURN_TO_VENDOR"

    # 调整
    COUNT_ADJUST = "COUNT_ADJUST"
