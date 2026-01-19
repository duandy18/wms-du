# app/services/order_ingest_routing/normalize.py
from __future__ import annotations

import os
from typing import Mapping, Optional


def normalize_province_from_address(address: Optional[Mapping[str, str]]) -> Optional[str]:
    """
    路线 C：province 来自订单收件省（省级默认规则）。

    合同（稳定版）：
    - province 只要非空就接受
    - 测试辅助：若省份缺失，可通过环境变量 WMS_TEST_DEFAULT_PROVINCE 提供默认值（仅测试用）
    """
    raw = None
    if address:
        raw = str(address.get("province") or "").strip()
        if raw:
            return raw

    fallback = (os.getenv("WMS_TEST_DEFAULT_PROVINCE") or "").strip()
    return fallback or None


def normalize_city_from_address(address: Optional[Mapping[str, str]]) -> Optional[str]:
    """
    路线 C：city 来自订单收件市（仅在省启用“按城市配置”时才要求）。

    合同（稳定版）：
    - city 只要非空就接受
    - 测试辅助：若 city 缺失，可通过环境变量 WMS_TEST_DEFAULT_CITY 提供默认值（仅测试用）
    """
    raw = None
    if address:
        raw = str(address.get("city") or "").strip()
        if raw:
            return raw

    fallback = (os.getenv("WMS_TEST_DEFAULT_CITY") or "").strip()
    return fallback or None
