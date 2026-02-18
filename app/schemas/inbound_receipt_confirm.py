# app/schemas/inbound_receipt_confirm.py
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.inbound_receipt import InboundReceiptOut


class InboundReceiptConfirmLedgerRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_line_key: str = Field(..., description="归一化行键（与 explain 一致）")
    ref: str = Field(..., description="落账 ref（建议使用 receipt.ref）")
    ref_line: int = Field(..., description="落账 ref_line（在 ref 维度递增）")
    item_id: int
    qty_delta: int
    idempotent: Optional[bool] = None
    applied: Optional[bool] = None


class InboundReceiptConfirmOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    receipt: InboundReceiptOut
    ledger_written: int = Field(..., description="本次实际写入的 ledger 行数（幂等时为 0）")
    ledger_refs: List[InboundReceiptConfirmLedgerRef] = Field(default_factory=list)
