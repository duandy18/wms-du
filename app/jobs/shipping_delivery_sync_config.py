# app/jobs/shipping_delivery_sync_config.py
from __future__ import annotations

from typing import Dict, Sequence

# 内部终态：这些一旦写入就不再被平台状态覆盖
INTERNAL_FINAL_STATUSES = {"DELIVERED", "LOST", "RETURNED"}

# 这里用“平台 → 内部状态 → 平台状态集合”的形式
# ⚠️ 里面的字符串请按你真实的平台状态码/文案调整
PLATFORM_STATUS_MAP: Dict[str, Dict[str, Sequence[str]]] = {
    # 示例：拼多多
    "PDD": {
        "DELIVERED": ["已签收", "TRADE_SUCCESS", "TRADE_FINISHED"],
        "RETURNED": ["已退货", "REFUND_SUCCESS"],
        "LOST": ["包裹丢失", "LOST"],
    },
    # 示例：京东
    "JD": {
        "DELIVERED": ["已签收", "FINISHED_L"],
        "RETURNED": ["已退货", "RETURNED"],
        "LOST": ["丢失", "LOST"],
    },
    # 其他平台按需扩展
}
