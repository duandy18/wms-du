# app/services/pick_task_commit_ship_handoff.py
from __future__ import annotations

from typing import Optional


class HandoffCodeError(ValueError):
    """
    轻量结构化异常：用于把 handoff 失败原因从“字符串”升级为“稳定字段”。
    不引入新概念，只是 ValueError 的一个子类，方便上层做 Problem 化输出。
    """

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        order_ref: str,
        expected: Optional[str] = None,
        got: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.reason = str(reason)
        self.order_ref = str(order_ref)
        self.expected = str(expected) if expected is not None else None
        self.got = str(got) if got is not None else None


def _normalize_wms_order_confirm_code_v1(*, platform: str, shop_id: str, ext_order_no: str) -> str:
    plat = (platform or "").upper().strip()
    shop = str(shop_id or "").strip()
    ext = str(ext_order_no or "").strip()
    return f"WMS:ORDER:v1:{plat}:{shop}:{ext}"


def expected_handoff_code_from_task_ref(*, ref: str) -> Optional[str]:
    """
    只接受订单 ref：ORD:{PLAT}:{shop}:{ext}
    返回期望的 WMS 订单确认码（v1，无签名）
    """
    if not isinstance(ref, str):
        return None
    if not ref.startswith("ORD:"):
        return None
    parts = ref.split(":", 3)
    if len(parts) != 4:
        return None
    _, plat, shop, ext = parts
    plat = (plat or "").upper().strip()
    shop = (shop or "").strip()
    ext = (ext or "").strip()
    if not plat or not shop or not ext:
        return None
    return _normalize_wms_order_confirm_code_v1(platform=plat, shop_id=shop, ext_order_no=ext)


def assert_handoff_code_match(*, order_ref: str, handoff_code: Optional[str]) -> None:
    """
    Phase 2：确认码已废弃
    - handoff_code 为空/缺省：不再作为门禁，直接跳过校验（✅ 主线）
    - handoff_code 非空：仍按旧规则做一致性校验（✅ 兼容旧客户端/风控场景）
    """
    got = (str(handoff_code or "").strip() or None)
    if got is None:
        return

    expected = expected_handoff_code_from_task_ref(ref=order_ref)
    if not expected:
        raise HandoffCodeError(
            f"handoff_code invalid: task.ref is not a valid order ref (expected ORD:*), ref={order_ref}",
            reason="invalid_ref",
            order_ref=str(order_ref),
            expected=None,
            got=got,
        )

    if got != expected:
        raise HandoffCodeError(
            "handoff_code not match",
            reason="mismatch",
            order_ref=str(order_ref),
            expected=str(expected),
            got=str(got),
        )
