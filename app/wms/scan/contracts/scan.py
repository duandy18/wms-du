# app/wms/scan/contracts/scan.py
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ScanRequest(BaseModel):
    """
    /scan 已收口为 pick probe 工具层。

    - mode 固定为 pick
    - probe 固定为 true
    - 只负责商品 / 包装识别，不承担库存执行
    - lot_code 是唯一批次展示码入参；batch_code alias 已退役
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    mode: Literal["pick"] = Field(default="pick", description="固定为 pick，仅用于拣货扫码 probe")
    item_id: Optional[int] = Field(None, description="商品 ID")
    qty: Optional[int] = Field(1, ge=0, description="本次识别数量，缺省为 1")
    barcode: Optional[str] = Field(None, description="原始扫码内容（可选）")
    warehouse_id: Optional[int] = Field(None, description="仓库 ID（可选）")

    lot_code: Optional[str] = Field(None, description="Lot 展示码")

    production_date: Optional[str] = Field(None, description="生产日期，建议 YYYY-MM-DD 或 YYYYMMDD")
    expiry_date: Optional[str] = Field(None, description="到期日期，建议 YYYY-MM-DD 或 YYYYMMDD")

    task_line_id: Optional[int] = Field(None, description="拣货任务行 ID（可选）")
    probe: Literal[True] = Field(default=True, description="固定为 true，仅做 probe")
    ctx: Optional[Dict[str, Any]] = Field(default=None, description="扩展上下文（device_id/operator 等）")


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
    production_date: Optional[str] = None
    expiry_date: Optional[str] = None

    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[Dict[str, Any]] = Field(default_factory=list)
