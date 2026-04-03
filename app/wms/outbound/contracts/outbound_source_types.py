from __future__ import annotations

from typing import Literal

OutboundSourceType = Literal["direct", "upstream"]

OUTBOUND_SOURCE_TYPE_DIRECT: OutboundSourceType = "direct"
OUTBOUND_SOURCE_TYPE_UPSTREAM: OutboundSourceType = "upstream"

OUTBOUND_SOURCE_TYPES: tuple[OutboundSourceType, ...] = (
    OUTBOUND_SOURCE_TYPE_DIRECT,
    OUTBOUND_SOURCE_TYPE_UPSTREAM,
)

__all__ = [
    "OutboundSourceType",
    "OUTBOUND_SOURCE_TYPE_DIRECT",
    "OUTBOUND_SOURCE_TYPE_UPSTREAM",
    "OUTBOUND_SOURCE_TYPES",
]
