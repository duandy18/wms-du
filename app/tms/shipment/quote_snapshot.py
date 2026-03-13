# app/tms/shipment/quote_snapshot.py
from __future__ import annotations

# 兼容层说明：
# - QuoteSnapshot 的主合同已迁移到 app.tms.quote_snapshot
# - 本文件仅作为过渡兼容层保留，避免旧 import 立即失效
# - 新代码应直接从 app.tms.quote_snapshot 导入

from app.tms.quote_snapshot import (
    extract_cost_estimated,
    extract_quote_snapshot,
    validate_quote_snapshot,
)

__all__ = [
    "extract_cost_estimated",
    "extract_quote_snapshot",
    "validate_quote_snapshot",
]
