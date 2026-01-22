# app/services/order_ingest_routing/normalize.py
from __future__ import annotations

from typing import Mapping, Optional


def normalize_province_from_address(address: Optional[Mapping[str, str]]) -> Optional[str]:
    """
    Phase 5 合同（稳定版）：
    - province 必须来自订单 address.province（显式输入）
    - 不允许任何 env fallback（避免测试/运行期产生“暗门”）
    """
    if not address:
        return None
    raw = str(address.get("province") or "").strip()
    return raw or None


def normalize_city_from_address(address: Optional[Mapping[str, str]]) -> Optional[str]:
    """
    Phase 5 合同（稳定版）：
    - city 必须来自订单 address.city（显式输入）
    - 仅当省启用 city-split 时才会被要求；但 normalize 本身不做 fallback
    """
    if not address:
        return None
    raw = str(address.get("city") or "").strip()
    return raw or None
