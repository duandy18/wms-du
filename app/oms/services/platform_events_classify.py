# app/oms/services/platform_events_classify.py
from __future__ import annotations



_PAID_ALIASES = {
    "PAID",
    "PAID_OK",
    "NEW",
    "CREATED",
    "WAIT_SELLER_SEND_GOODS",
}
_CANCEL_ALIASES = {
    "CANCELED",
    "CANCELLED",
    "VOID",
    "TRADE_CLOSED",
}
_SHIPPED_ALIASES = {
    "SHIPPED",
    "DELIVERED",
    "WAIT_BUYER_CONFIRM_GOODS",
    "TRADE_FINISHED",
}


def classify(state: str) -> str:
    """
    Phase 5：彻底消除“预占/RESERVE”概念后，平台事件只分三类动作：

    - PICK  ：进入执行准备主线（历史语义残留；当前不再走 pick_task 公共主线）
    - CANCEL：取消执行态（撤销拣货任务等）
    - SHIP  ：外部平台发货态；不再自动扣 WMS 库存，正式执行由 WMS outbound submit 承担
    """
    u = (state or "").upper()
    if u in _PAID_ALIASES:
        return "PICK"
    if u in _CANCEL_ALIASES:
        return "CANCEL"
    if u in _SHIPPED_ALIASES:
        return "SHIP"
    return "IGNORE"
