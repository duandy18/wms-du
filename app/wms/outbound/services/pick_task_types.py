# app/services/pick_task_types.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class PickTaskCommitLine:
    item_id: int
    req_qty: int
    picked_qty: int
    warehouse_id: int
    batch_code: Optional[str]
    order_id: Optional[int] = None


@dataclass
class PickTaskDiffLine:
    """
    差异按 item_id 汇总：

    - req_qty    : 该 item 的总计划量（仅统计来自订单的行，即 order_id 非空）
    - picked_qty : 该 item 的总拣货量（所有行 picked 之和）
    - delta      : picked_qty - req_qty
    - status:
        "OK"     : picked == req
        "UNDER"  : picked <  req
        "OVER"   : picked >  req
    """

    item_id: int
    req_qty: int
    picked_qty: int
    delta: int
    status: str


@dataclass
class PickTaskDiffSummary:
    task_id: int
    lines: List[PickTaskDiffLine]
    has_over: bool
    has_under: bool
