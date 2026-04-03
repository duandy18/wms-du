from __future__ import annotations

from typing import Literal

InboundSourceType = Literal["direct", "upstream"]

INBOUND_SOURCE_TYPE_DIRECT: InboundSourceType = "direct"
INBOUND_SOURCE_TYPE_UPSTREAM: InboundSourceType = "upstream"

INBOUND_SOURCE_TYPES: tuple[InboundSourceType, ...] = (
    INBOUND_SOURCE_TYPE_DIRECT,
    INBOUND_SOURCE_TYPE_UPSTREAM,
)

__all__ = [
    "InboundSourceType",
    "INBOUND_SOURCE_TYPE_DIRECT",
    "INBOUND_SOURCE_TYPE_UPSTREAM",
    "INBOUND_SOURCE_TYPES",
]
