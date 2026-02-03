# app/api/routers/scan_schemas.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ==========================
# Request / Response models
# ==========================


def _is_forbidden_none_token(s: Optional[str]) -> bool:
    if s is None:
        return False
    return s.strip().lower() == "none"


def _is_blank(s: Optional[str]) -> bool:
    if s is None:
        return True
    return s.strip() == ""


class ScanRequest(BaseModel):
    """
    v2 通用 Scan 请求体（与前端 ScanRequest 对齐）：

    - mode: "receive" | "pick" | "count"
    - item_id + qty: 主参数
    - warehouse_id: 仓库维度（当前版本已无 scan-level location 概念）
    - batch_code / production_date / expiry_date: 猫粮批次/保质期信息
    - task_line_id: 拣货任务行（mode=pick 时可用）
    - probe: 探针模式，只试算不落账
    - ctx: 扩展上下文（device_id / operator 等），用于生成 scan_ref 与审计
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    mode: str = Field(..., description="receive | pick | count")

    item_id: Optional[int] = Field(None, description="商品 ID")
    qty: Optional[int] = Field(1, ge=0, description="本次扫描数量，缺省为 1")

    # 原始条码内容（可选；可传 GS1 串）
    barcode: Optional[str] = Field(None, description="原始扫码内容（可选）")

    # v2：只认仓库，不认库位
    warehouse_id: Optional[int] = Field(None, description="仓库 ID（缺省时由后端兜底为 1）")

    # 批次 / 日期信息（语义由 API 合同层判定）
    batch_code: Optional[str] = Field(None, description="批次编码（可选；批次语义由 API 合同层判定）")
    production_date: Optional[str] = Field(None, description="生产日期，建议 YYYY-MM-DD 或 YYYYMMDD")
    expiry_date: Optional[str] = Field(None, description="到期日期，建议 YYYY-MM-DD 或 YYYYMMDD")

    # 拣货任务行
    task_line_id: Optional[int] = Field(None, description="拣货任务行 ID（mode=pick 时可用）")

    # 探针模式：只试算不落账
    probe: bool = Field(False, description="探针模式，仅试算不落账")

    # 扩展上下文
    ctx: Optional[Dict[str, Any]] = Field(default=None, description="扩展上下文（device_id/operator 等）")


# ========== 旧模型：仅用于 legacy 接口 / 测试兼容，/scan 已不再使用 ==========


class ScanReceiveRequest(BaseModel):
    """
    LEGACY：旧版 /scan（receive）专用模型，带 location_id/ref/occurred_at。
    新架构下，/scan 已使用 ScanRequest，不再依赖本模型。
    """

    model_config = ConfigDict(str_strip_whitespace=True)
    mode: str = Field(..., description="固定 'receive'")
    item_id: int
    location_id: int
    qty: int = Field(..., ge=0)
    ref: str
    batch_code: Optional[str] = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    production_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    warehouse_id: Optional[int] = None

    @model_validator(mode="after")
    def _check(self) -> "ScanReceiveRequest":
        if self.mode.lower() != "receive":
            raise ValueError("unsupported scan mode; only 'receive' is allowed here")

        # 不在 schema 强行要求 batch_code 非空（是否必须由 item.has_shelf_life 决定，应在 API 合同层处理）
        if self.batch_code is not None:
            if _is_blank(self.batch_code):
                raise ValueError("batch_code cannot be empty string; use null when not applicable.")
            if _is_forbidden_none_token(self.batch_code):
                raise ValueError("batch_code must not be 'none' (case-insensitive).")

        if self.production_date is None and self.expiry_date is None:
            raise ValueError("猫粮收货必须提供 production_date 或 expiry_date（至少一项）。")
        if self.occurred_at.tzinfo is None:
            self.occurred_at = self.occurred_at.replace(tzinfo=timezone.utc)
        return self


class ScanCountCommitRequest(BaseModel):
    """
    LEGACY：基于 location 的盘点请求。
    当前 /scan/count/commit 仍按旧合同工作，未来可并入 /scan + ScanRequest(mode='count')。
    """

    model_config = ConfigDict(str_strip_whitespace=True)
    item_id: int
    location_id: int
    qty: int = Field(..., ge=0, description="盘点后的绝对量")
    ref: str
    batch_code: Optional[str] = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    production_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None

    @model_validator(mode="after")
    def _check(self) -> "ScanCountCommitRequest":
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
    # 可选回显
    item_id: Optional[int] = None
    location_id: Optional[int] = None
    qty: Optional[int] = None
    batch_code: Optional[str] = None

    # v2：盘点 / 收货 enriched 字段（按仓库 + 商品 + 批次）
    warehouse_id: Optional[int] = None
    actual: Optional[int] = None
    before: Optional[int] = None
    before_qty: Optional[int] = None
    after: Optional[int] = None
    after_qty: Optional[int] = None
    delta: Optional[int] = None
    production_date: Optional[str] = None
    expiry_date: Optional[str] = None

    # v2：承接 orchestrator 的审计信息
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[Dict[str, Any]] = Field(default_factory=list)
