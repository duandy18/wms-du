# app/tms/quote_snapshot/__init__.py
"""
TMS / QuoteSnapshot module.

语义定位：
- QuoteSnapshot 是 TransportQuote 产出的执行证据包
- Shipment 只消费，不定义其主合同

当前提供：
- build_quote_snapshot: 统一构建 snapshot
- extract_quote_snapshot: 从 meta 中提取 snapshot
- validate_quote_snapshot: 校验 snapshot 基本合同
- extract_selected_quote: 从 snapshot 中提取 selected_quote
- extract_cost_estimated: 从 snapshot 中提取 total_amount
- extract_freight_estimated: 从 snapshot.breakdown.summary 中提取 base_amount
- extract_surcharge_estimated: 从 snapshot.breakdown.summary 中提取 surcharge_amount
- QuoteSnapshotData / QuoteSnapshotSelectedQuote: TMS 内部合同类型
"""

from .builder import build_quote_snapshot
from .contracts import (
    QUOTE_SNAPSHOT_VERSION,
    QuoteSnapshotData,
    QuoteSnapshotInputPayload,
    QuoteSnapshotSelectedQuote,
    QuoteSnapshotSelectedQuotePayload,
)
from .validator import (
    extract_cost_estimated,
    extract_freight_estimated,
    extract_quote_snapshot,
    extract_selected_quote,
    extract_surcharge_estimated,
    validate_quote_snapshot,
)

__all__ = [
    "QUOTE_SNAPSHOT_VERSION",
    "QuoteSnapshotData",
    "QuoteSnapshotInputPayload",
    "QuoteSnapshotSelectedQuote",
    "QuoteSnapshotSelectedQuotePayload",
    "build_quote_snapshot",
    "extract_cost_estimated",
    "extract_freight_estimated",
    "extract_quote_snapshot",
    "extract_selected_quote",
    "extract_surcharge_estimated",
    "validate_quote_snapshot",
]
