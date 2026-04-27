from __future__ import annotations

from pydantic import BaseModel


class PddFactBridgeDataOut(BaseModel):
    platform: str
    store_id: int
    store_code: str
    pdd_order_id: int
    ext_order_no: str
    lines_count: int
    facts_written: int


class PddFactBridgeEnvelopeOut(BaseModel):
    ok: bool
    data: PddFactBridgeDataOut
