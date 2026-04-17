from __future__ import annotations

from typing import Literal

InboundReceiptSourceType = Literal[
    "PURCHASE_ORDER",
    "MANUAL",
    "RETURN_ORDER",
]

InboundReceiptStatus = Literal[
    "DRAFT",
    "RELEASED",
    "VOIDED",
]

__all__ = [
    "InboundReceiptSourceType",
    "InboundReceiptStatus",
]
