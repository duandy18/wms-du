# app/wms/scan/contracts/scan.py
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _normalize_alias_pair(
    *,
    lot_code: Optional[str],
    batch_code: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """
    lot_code：正名
    batch_code：历史兼容字段名
    """
    lc = lot_code
    bc = batch_code
    if lc is None and bc is None:
        return None, None
    if lc is None:
        return bc, bc
    if bc is None:
        return lc, lc
    if str(lc) != str(bc):
        raise ValueError("lot_code and batch_code must be identical when both provided.")
    return lc, bc


class ScanRequest(BaseModel):
    """
    /scan 已收口为 pick probe 工具层。

    - mode 固定为 pick
    - probe 固定为 true
    - 只负责商品 / 包装识别，不承担库存执行
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    mode: Literal["pick"] = Field(default="pick", description="固定为 pick，仅用于拣货扫码 probe")
    item_id: Optional[int] = Field(None, description="商品 ID")
    qty: Optional[int] = Field(1, ge=0, description="本次识别数量，缺省为 1")
    barcode: Optional[str] = Field(None, description="原始扫码内容（可选）")
    warehouse_id: Optional[int] = Field(None, description="仓库 ID（可选）")

    lot_code: Optional[str] = Field(None, description="Lot 展示码（正名；等价于 batch_code）")
    batch_code: Optional[str] = Field(None, description="批次编码（兼容字段；等价于 lot_code）")

    production_date: Optional[str] = Field(None, description="生产日期，建议 YYYY-MM-DD 或 YYYYMMDD")
    expiry_date: Optional[str] = Field(None, description="到期日期，建议 YYYY-MM-DD 或 YYYYMMDD")

    task_line_id: Optional[int] = Field(None, description="拣货任务行 ID（可选）")
    probe: Literal[True] = Field(default=True, description="固定为 true，仅做 probe")
    ctx: Optional[Dict[str, Any]] = Field(default=None, description="扩展上下文（device_id/operator 等）")

    @model_validator(mode="after")
    def _alias_lot_code(self) -> "ScanRequest":
        lc, bc = _normalize_alias_pair(lot_code=self.lot_code, batch_code=self.batch_code)
        self.lot_code = lc
        self.batch_code = bc
        return self


class ScanResponse(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    ok: bool = True
    committed: bool = False
    scan_ref: str
    event_id: Optional[int] = None
    source: str

    item_id: Optional[int] = None
    item_uom_id: Optional[int] = None
    ratio_to_base: Optional[int] = None
    qty: Optional[int] = None
    qty_base: Optional[int] = None

    lot_code: Optional[str] = None
    batch_code: Optional[str] = None
    production_date: Optional[str] = None
    expiry_date: Optional[str] = None

    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[Dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _alias_lot_code(self) -> "ScanResponse":
        lc, bc = _normalize_alias_pair(lot_code=self.lot_code, batch_code=self.batch_code)
        self.lot_code = lc
        self.batch_code = bc
        return self
