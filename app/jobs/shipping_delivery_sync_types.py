# app/jobs/shipping_delivery_sync_types.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class PlatformOrderStatus:
    platform: str
    shop_id: str
    ext_order_no: str
    platform_status: str  # 平台原始状态码/文案
    internal_status: Optional[str]  # 映射后的内部状态：DELIVERED/RETURNED/LOST/None
    delivered_at: Optional[datetime]  # 若能从平台拿到签收时间就丢这里
    raw_payload: Dict[str, Any]
