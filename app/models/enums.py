# app/models/enums.py
from __future__ import annotations

try:
    from enum import StrEnum  # Python 3.11+
except ImportError:  # 兼容更低版本
    from enum import Enum as StrEnum  # type: ignore


class FlowType(StrEnum):
    """
    扫码/作业编排用的流程维度（不直接写入台账 reason）：

    - RECEIVE     收货（供应商收货 / 客户退货入库）
    - PUTAWAY     上架
    - COUNT       盘点
    - PICK        拣选
    - SHIP        发货 / 出库
    - RELOCATE    移库/转移
    - ADJUST      调整/纠偏（编排层面用；真正记账请走 MovementType）
    """

    RECEIVE = "RECEIVE"
    PUTAWAY = "PUTAWAY"
    COUNT = "COUNT"
    PICK = "PICK"
    SHIP = "SHIP"
    RELOCATE = "RELOCATE"
    ADJUST = "ADJUST"


class MovementType(StrEnum):
    """
    业务 → DB movementtype 的映射（落入库存台账 stock_ledger.reason）：

    核心四类：
    - RECEIPT     入库（供应商收货 / 客户退货入库等）
    - SHIPMENT    出库（发货 / 采购退货 / 出仓等）
    - TRANSFER    转移（上架 / 移库 / 仓间调拨）
    - ADJUSTMENT  调整（盘点差异 / 报废 / 手工纠偏）

    注意：
    - 这里定义的“别名”都是业务层的语义映射，真正落库只认上面的四个核心值。
    """

    # === 数据库存储的核心值 ===
    RECEIPT = "RECEIPT"
    SHIPMENT = "SHIPMENT"
    TRANSFER = "TRANSFER"
    ADJUSTMENT = "ADJUSTMENT"

    # === 入库相关（正数 delta） ===
    # 供应商收货 / 普通入库
    RECEIVE = "RECEIPT"
    INBOUND = "RECEIPT"

    # 客户退货入库 / RMA 回仓
    RETURN_IN = "RECEIPT"
    RETURN_CUSTOMER = "RECEIPT"
    RMA_IN = "RECEIPT"

    # 为兼容旧代码，RETURN 保留为“入库退货”别名
    RETURN = "RECEIPT"

    # === 上架 / 移库 / 仓间转移（delta 正负均可） ===
    PUTAWAY = "TRANSFER"
    MOVE = "TRANSFER"
    RELOCATE = "TRANSFER"
    TRANSFER_OUT = "TRANSFER"
    TRANSFER_IN = "TRANSFER"

    # === 拣选 / 打包 / 盘点调整（通常 delta 正负都有） ===
    PICK = "ADJUSTMENT"
    PACK = "ADJUSTMENT"
    COUNT = "ADJUSTMENT"
    ADJUST = "ADJUSTMENT"

    # === 出库 / 发货（负数 delta） ===
    SHIP = "SHIPMENT"
    SHIPMENT_ALIAS = "SHIPMENT"
    OUTBOUND = "SHIPMENT"
    DISPATCH = "SHIPMENT"

    # 采购退货（退给供应商）：属于出库方向
    # 建议在 ReturnTaskService.commit 中使用 RETURN_OUT / RETURN_SUPPLIER / RTV
    RETURN_OUT = "SHIPMENT"
    RETURN_SUPPLIER = "SHIPMENT"
    RTV = "SHIPMENT"  # Return-To-Vendor 常用缩写

    # === 报废 / 纠偏等（通常走调整） ===
    SCRAP = "ADJUSTMENT"
    CORRECT = "ADJUSTMENT"


__all__ = ["FlowType", "MovementType"]
