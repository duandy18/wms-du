# app/oms/services/order_ref_helper.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

ORD_PREFIX = "ORD:"


@dataclass(frozen=True)
class OrderRef:
    """
    统一表示一个订单业务键：
    - platform: 大写（PDD / TAOBAO ...）
    - store_code: 字符串（保持原样）
    - ext_order_no: 外部订单号（保持原样）
    """

    platform: str
    store_code: str
    ext_order_no: str


def make_order_ref(platform: str, store_code: str, ext_order_no: str) -> str:
    """
    统一生成订单 ref：
      ORD:{PLATFORM}:{store_code}:{ext_order_no}
    """
    plat = (platform or "").upper().strip()
    if not plat:
        raise ValueError("platform is required for order ref")
    if not store_code:
        raise ValueError("store_code is required for order ref")
    if not ext_order_no:
        raise ValueError("ext_order_no is required for order ref")
    return f"{ORD_PREFIX}{plat}:{store_code}:{ext_order_no}"


def parse_order_ref(ref: str) -> Optional[OrderRef]:
    """
    尝试解析一个订单 ref：

      "ORD:{PLATFORM}:{store_code}:{ext_order_no}"
        → OrderRef(PLATFORM, store_code, ext_order_no)

    若格式不合法，返回 None（不抛异常，方便“软约束”场景使用）。
    """
    if not isinstance(ref, str):
        return None
    if not ref.startswith(ORD_PREFIX):
        return None

    # 期待 "ORD:PLAT:STORE:EXT" 共 4 段
    parts = ref.split(":", 3)
    if len(parts) != 4:
        return None

    _, plat, store_code, ext_no = parts
    plat = (plat or "").upper().strip()
    store_code = (store_code or "").strip()
    ext_no = (ext_no or "").strip()
    if not plat or not store_code or not ext_no:
        return None

    return OrderRef(platform=plat, store_code=store_code, ext_order_no=ext_no)
