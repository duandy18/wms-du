# app/wms/scan/contracts/scan.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _is_forbidden_none_token(s: Optional[str]) -> bool:
    if s is None:
        return False
    return s.strip().lower() == "none"


def _is_blank(s: Optional[str]) -> bool:
    if s is None:
        return True
    return s.strip() == ""


def _normalize_alias_pair(*, lot_code: Optional[str], batch_code: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """
    Phase M-4 governance（合同双轨）：

    - lot_code：正名（lot-world 语义）
    - batch_code：历史兼容字段名（旧客户端继续用）

    规则：
    - 只传其一：两者对齐为同一值（字符串保持原样；trim 由 ConfigDict 负责）
    - 两者都传且不一致：直接 422（ValueError）
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
    v2 通用 Scan 请求体（与前端 ScanRequest 对齐）：
    - warehouse_id: 仓库维度（当前版本已无 scan-level location 概念）

    Phase M-4 governance：
    - lot_code 为正名；batch_code 保留兼容别名
    - 内部执行链路暂继续使用 batch_code 作为 key（后续阶段再逐步收口）
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    mode: str = Field(..., description="receive | pick | count")
    item_id: Optional[int] = Field(None, description="商品 ID")
    qty: Optional[int] = Field(1, ge=0, description="本次扫描数量，缺省为 1")
    barcode: Optional[str] = Field(None, description="原始扫码内容（可选）")
    warehouse_id: Optional[int] = Field(None, description="仓库 ID（缺省时由后端兜底为 1）")

    # ✅ 合同双轨：lot_code 正名 + batch_code 兼容
    lot_code: Optional[str] = Field(None, description="Lot 展示码（优先使用；等价于 batch_code）")
    batch_code: Optional[str] = Field(None, description="批次编码（兼容字段；等价于 lot_code）")

    production_date: Optional[str] = Field(None, description="生产日期，建议 YYYY-MM-DD 或 YYYYMMDD")
    expiry_date: Optional[str] = Field(None, description="到期日期，建议 YYYY-MM-DD 或 YYYYMMDD")

    task_line_id: Optional[int] = Field(None, description="拣货任务行 ID（mode=pick 时可用）")
    probe: bool = Field(False, description="探针模式，仅试算不落账")
    ctx: Optional[Dict[str, Any]] = Field(default=None, description="扩展上下文（device_id/operator 等）")

    @model_validator(mode="after")
    def _alias_lot_code(self) -> "ScanRequest":
        lc, bc = _normalize_alias_pair(lot_code=self.lot_code, batch_code=self.batch_code)
        self.lot_code = lc
        self.batch_code = bc
        return self


class ScanCountCommitRequest(BaseModel):
    """
    盘点提交（warehouse 粒度）。

    Phase M-4 governance：
    - lot_code 正名；batch_code 兼容别名
    """

    model_config = ConfigDict(str_strip_whitespace=True)
    item_id: int
    warehouse_id: int
    qty: int = Field(..., ge=0, description="盘点后的绝对量")
    ref: str

    lot_code: Optional[str] = Field(None, description="Lot 展示码（优先使用；等价于 batch_code）")
    batch_code: Optional[str] = Field(None, description="批次编码（兼容字段；等价于 lot_code）")

    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    production_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None

    @model_validator(mode="after")
    def _check(self) -> "ScanCountCommitRequest":
        # alias 对齐
        lc, bc = _normalize_alias_pair(lot_code=self.lot_code, batch_code=self.batch_code)
        self.lot_code = lc
        self.batch_code = bc

        if self.batch_code is not None:
            if _is_blank(self.batch_code):
                raise ValueError("batch_code cannot be empty string; use null when not applicable.")
            if _is_forbidden_none_token(self.batch_code):
                raise ValueError("batch_code must not be 'none' (case-insensitive).")
        if self.production_date is None and self.expiry_date is None:
            raise ValueError("猫粮盘点必须提供 production_date 或 expiry_date（至少一项）。")
        if self.occurred_at.tzinfo is None:
            self.occurred_at = self.occurred_at.replace(tzinfo=timezone.utc)
        return self


class ScanResponse(BaseModel):
    ok: bool = True
    committed: bool = True
    scan_ref: str
    event_id: Optional[int] = None
    source: str

    item_id: Optional[int] = None
    item_uom_id: Optional[int] = None
    ratio_to_base: Optional[int] = None
    qty: Optional[int] = None
    qty_base: Optional[int] = None

    # ✅ 合同双轨：lot_code 正名 + batch_code 兼容
    lot_code: Optional[str] = None
    batch_code: Optional[str] = None

    warehouse_id: Optional[int] = None
    actual: Optional[int] = None
    before: Optional[int] = None
    before_qty: Optional[int] = None
    after: Optional[int] = None
    after_qty: Optional[int] = None
    delta: Optional[int] = None
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
