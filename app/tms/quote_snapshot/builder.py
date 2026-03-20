# app/tms/quote_snapshot/builder.py
from __future__ import annotations

from typing import Any

from .contracts import (
    QUOTE_SNAPSHOT_VERSION,
    QuoteSnapshotData,
    QuoteSnapshotInputPayload,
    QuoteSnapshotSelectedQuote,
    QuoteSnapshotSelectedQuotePayload,
)


def _safe_dict(value: Any) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _safe_list_of_str(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x) for x in value]


def build_quote_snapshot(
    *,
    source: str,
    input_payload: QuoteSnapshotInputPayload,
    selected_quote: QuoteSnapshotSelectedQuotePayload,
) -> QuoteSnapshotData:
    """
    构建统一 QuoteSnapshot 合同。

    约定：
    - source: 生成来源，例如 shipping_quote.calc / shipping_quote.recommend
    - input: 原始输入证据（通常来自请求 payload）
    - selected_quote: 被选中的报价结果（或 calc 直接结果）
    """
    selected = dict(selected_quote)

    snapshot_selected_quote: QuoteSnapshotSelectedQuote = {
        "quote_status": str(selected.get("quote_status") or "OK"),
        "template_id": selected.get("template_id"),
        "template_name": selected.get("template_name"),
        "provider_id": selected.get("provider_id"),
        "carrier_code": selected.get("carrier_code"),
        "carrier_name": selected.get("carrier_name"),
        "currency": selected.get("currency"),
        "total_amount": selected.get("total_amount"),
        "weight": _safe_dict(selected.get("weight")),
        "destination_group": selected.get("destination_group"),
        "pricing_matrix": selected.get("pricing_matrix"),
        "breakdown": _safe_dict(selected.get("breakdown")),
        "reasons": _safe_list_of_str(selected.get("reasons")),
    }

    snapshot: QuoteSnapshotData = {
        "version": QUOTE_SNAPSHOT_VERSION,
        "source": str(source),
        "input": dict(input_payload),
        "selected_quote": snapshot_selected_quote,
    }
    return snapshot
