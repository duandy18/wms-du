# app/shipping_assist/quote_snapshot/contracts.py
from __future__ import annotations

from typing import Any, Mapping, TypedDict

QUOTE_SNAPSHOT_VERSION = "v1"


class QuoteSnapshotSelectedQuote(TypedDict):
    quote_status: str
    template_id: int | None
    template_name: str | None
    provider_id: int | None
    shipping_provider_code: str | None
    shipping_provider_name: str | None
    currency: str | None
    total_amount: float | int
    weight: dict[str, object]
    destination_group: object | None
    pricing_matrix: object | None
    breakdown: dict[str, object]
    reasons: list[str]


class QuoteSnapshotData(TypedDict):
    version: str
    source: str
    input: dict[str, object]
    selected_quote: QuoteSnapshotSelectedQuote


QuoteSnapshotInputPayload = Mapping[str, Any]
QuoteSnapshotSelectedQuotePayload = Mapping[str, Any]
