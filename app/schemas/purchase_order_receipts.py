# app/schemas/purchase_order_receipts.py
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PurchaseOrderReceiptEventOut(BaseModel):
    """
    采购单“历史收货事实”（用于 UI 展示与审计）。
    口径：直接来自 stock_ledger（reason=RECEIPT, ref=PO-{po_id}）。
    """

    ref: str = Field(..., description="引用，如 PO-123")
    ref_line: int = Field(..., gt=0, description="ref 内顺序号（与台账一致）")

    warehouse_id: int = Field(..., gt=0, description="仓库")
    item_id: int = Field(..., gt=0, description="商品 ID")
    line_no: Optional[int] = Field(None, description="采购单行号（若可映射）")

    batch_code: str = Field(..., description="批次号（事实键）")
    qty: int = Field(..., description="本次收货数量（delta）")
    after_qty: int = Field(..., description="收货后库存余额（after_qty）")

    occurred_at: datetime = Field(..., description="发生时间（事实时间）")
    production_date: Optional[date] = Field(None, description="生产日期（可空）")
    expiry_date: Optional[date] = Field(None, description="到期日期（可空）")

    model_config = ConfigDict(from_attributes=True)
