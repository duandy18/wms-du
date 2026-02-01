# app/services/pick_task_commit_ship_handoff.py
from __future__ import annotations

from typing import Optional


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


def assert_handoff_code_match(*, order_ref: str, handoff_code: str) -> None:
    expected = expected_handoff_code_from_task_ref(ref=order_ref)
    if not expected:
        raise ValueError(
            f"handoff_code invalid: task.ref is not a valid order ref (expected ORD:*), ref={order_ref}"
        )
    got = str(handoff_code or "").strip()
    if not got:
        raise ValueError("handoff_code invalid: empty")
    if got != expected:
        raise ValueError(f"handoff_code not match: expected={expected}, got={got}")
