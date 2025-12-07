from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.gateway.scan_orchestrator import ingest as ingest_scan
from app.models.enums import MovementType
from app.services.stock_service import StockService

router = APIRouter(tags=["scan"])


def _to_date_str(v: Any) -> Optional[str]:
    """
    将 date / datetime / str 统一转为 'YYYY-MM-DD' 字符串，其他类型兜底为 str(v)。
    用于 ScanResponse 的 production_date / expiry_date，避免 Pydantic 类型错误。
    """
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s or None
    if isinstance(v, datetime):
        return v.date().isoformat()
    try:
        iso = getattr(v, "isoformat", None)
        if callable(iso):
            return iso()
    except Exception:
        pass
    return str(v)


# ==========================
# Request / Response models
# ==========================


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

    # 猫粮批次 / 日期信息
    batch_code: Optional[str] = Field(None, description="批次编码（可选）")
    production_date: Optional[str] = Field(
        None, description="生产日期，建议 YYYY-MM-DD 或 YYYYMMDD"
    )
    expiry_date: Optional[str] = Field(None, description="到期日期，建议 YYYY-MM-DD 或 YYYYMMDD")

    # 拣货任务行
    task_line_id: Optional[int] = Field(None, description="拣货任务行 ID（mode=pick 时可用）")

    # 探针模式：只试算不落账
    probe: bool = Field(False, description="探针模式，仅试算不落账")

    # 扩展上下文
    ctx: Optional[Dict[str, Any]] = Field(
        default=None, description="扩展上下文（device_id/operator 等）"
    )


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
    batch_code: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    production_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    warehouse_id: Optional[int] = None

    @model_validator(mode="after")
    def _check(self) -> "ScanReceiveRequest":
        if self.mode.lower() != "receive":
            raise ValueError("unsupported scan mode; only 'receive' is allowed here")
        if not self.batch_code:
            raise ValueError("猫粮收货必须提供 batch_code。")
        if self.production_date is None and self.expiry_date is None:
            raise ValueError("猫粮收货必须提供 production_date 或 expiry_date（至少一项）。")
        if self.occurred_at.tzinfo is None:
            self.occurred_at = self.occurred_at.replace(tzinfo=timezone.utc)
        return self


class ScanPutawayCommitRequest(BaseModel):
    """
    LEGACY：基于 location 的上架 / 移库请求。
    当前无 scan-level location 概念，putaway 功能在扫描通路中已禁用。
    """

    model_config = ConfigDict(str_strip_whitespace=True)
    item_id: int
    from_location_id: int
    to_location_id: int
    qty: int = Field(..., ge=1)
    ref: str
    batch_code: str
    production_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    # 兼容历史/不同命名
    start_ref_line: Optional[int] = None
    left_ref_line: Optional[int] = None
    warehouse_id: Optional[int] = None

    @model_validator(mode="after")
    def _check(self) -> "ScanPutawayCommitRequest":
        if not self.batch_code:
            raise ValueError("猫粮搬运必须提供 batch_code。")
        if self.production_date is None and self.expiry_date is None:
            raise ValueError("猫粮搬运必须提供 production_date 或 expiry_date（至少一项）。")
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
    batch_code: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    production_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None

    @model_validator(mode="after")
    def _check(self) -> "ScanCountCommitRequest":
        if not self.batch_code:
            raise ValueError("猫粮盘点必须提供 batch_code。")
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


# ==========================
# /scan（统一入口 → orchestrator）
# ==========================


@router.post("/scan", response_model=ScanResponse, status_code=status.HTTP_200_OK)
async def scan_entrypoint(
    req: ScanRequest,
    session: AsyncSession = Depends(get_session),
) -> ScanResponse:
    """
    v2 统一 /scan 入口：

    - 前端提交 ScanRequest（mode + item_id + qty + warehouse_id + 批次/日期 + ctx）
    - 由 scan_orchestrator.ingest 解析并路由到对应 handler（receive/pick/count）
    - 不再直接调用 InboundService.receive，也不再依赖 location_id/ref/occurred_at
    """
    result = await ingest_scan(req.model_dump(), session)

    # ★ item_id：优先 orchestrator，其次请求体
    item_id = result.get("item_id") or req.item_id

    # qty / batch_code 仍以请求体为主（count 模式下 actual 单独返回）
    qty = req.qty
    batch_code = req.batch_code

    # enriched 字段（count / receive）
    warehouse_id = result.get("warehouse_id") or req.warehouse_id
    actual = result.get("actual")
    before = result.get("before")
    after = result.get("after")
    delta = result.get("delta")

    before_qty = result.get("before_qty") or before
    after_qty = result.get("after_qty") or after

    # 日期：优先 orchestrator，再回落到请求体，统一转为字符串
    raw_prod = result.get("production_date")
    if raw_prod is None:
        raw_prod = req.production_date
    prod = _to_date_str(raw_prod)

    raw_exp = result.get("expiry_date")
    if raw_exp is None:
        raw_exp = req.expiry_date
    exp = _to_date_str(raw_exp)

    return ScanResponse(
        ok=bool(result.get("ok", False)),
        committed=bool(result.get("committed", False)),
        scan_ref=result.get("scan_ref") or "",
        event_id=result.get("event_id"),
        source=result.get("source") or "scan_orchestrator",
        item_id=item_id,
        # 现阶段 scan 层无库位概念
        location_id=None,
        qty=qty,
        batch_code=batch_code,
        warehouse_id=warehouse_id,
        actual=actual,
        before=before,
        before_qty=before_qty,
        after=after,
        after_qty=after_qty,
        delta=delta,
        production_date=prod,
        expiry_date=exp,
        evidence=result.get("evidence") or [],
        errors=result.get("errors") or [],
    )


# ==========================
# /scan/putaway/commit（LEGACY：已禁用）
# ==========================


@router.post("/scan/putaway/commit", response_model=ScanResponse, status_code=status.HTTP_200_OK)
async def scan_putaway_commit(
    req: ScanPutawayCommitRequest,  # noqa: ARG001
    session: AsyncSession = Depends(get_session),  # noqa: ARG001
) -> ScanResponse:
    """
    业务上 scan 通路已无 location 概念，putaway 功能在扫描通路中禁用。
    保留该路由仅为兼容历史调用，统一返回 FEATURE_DISABLED。
    """
    return ScanResponse(
        ok=False,
        committed=False,
        scan_ref="",
        event_id=None,
        source="scan_putaway_disabled",
        errors=[
            {
                "stage": "putaway",
                "error": "FEATURE_DISABLED: putaway is not supported on /scan without locations",
            }
        ],
    )


# ==========================
# /scan/count/commit（legacy → 未来可并入 /scan）
# ==========================


@router.post("/scan/count/commit", response_model=ScanResponse, status_code=status.HTTP_200_OK)
async def scan_count_commit(
    req: ScanCountCommitRequest,
    session: AsyncSession = Depends(get_session),
) -> ScanResponse:
    """
    LEGACY：基于 location 的盘点接口。
    当前仍按旧实现工作，未来可迁移到 /scan + ScanRequest(mode='count')，并改用 warehouse_id 粒度。
    """
    svc = StockService()

    # 1) 解析/幂等建档 → batch_id
    try:
        batch_id = await svc._resolve_batch_id(
            session=session,
            item_id=req.item_id,
            location_id=req.location_id,
            batch_code=req.batch_code,
            production_date=req.production_date,
            expiry_date=req.expiry_date,
            warehouse_id=None,
            created_at=req.occurred_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"resolve batch failed: {e}")

    # 2) 以 (item,loc,batch_id) 读取 current（分支避免 asyncpg 类型歧义）
    if batch_id is None:
        sql = text(
            "SELECT COALESCE(SUM(qty),0) FROM stocks WHERE item_id=:i AND location_id=:l AND batch_id IS NULL"
        )
        params = {"i": req.item_id, "l": req.location_id}
    else:
        sql = text(
            "SELECT COALESCE(SUM(qty),0) FROM stocks WHERE item_id=:i AND location_id=:l AND batch_id=:b"
        )
        params = {"i": req.item_id, "l": req.location_id, "b": int(batch_id)}
    current_row = await session.execute(sql, params)
    current = int(current_row.scalar() or 0)

    # 3) delta = 目标 - 当前；落 COUNT 台账（即使 delta==0 也落，便于审计）
    delta = int(req.qty) - current
    try:
        await svc.adjust(
            session=session,
            item_id=req.item_id,
            location_id=req.location_id,
            delta=delta,
            reason=MovementType.COUNT,
            ref=req.ref,
            ref_line=1,
            occurred_at=req.occurred_at,
            batch_code=req.batch_code,
            production_date=req.production_date,
            expiry_date=req.expiry_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"scan(count) failed: {e}")

    scan_ref = f"scan:api:{req.occurred_at.isoformat(timespec='minutes')}"
    return ScanResponse(
        ok=True,
        committed=True,
        scan_ref=scan_ref,
        event_id=None,
        source="scan_count_commit",
        item_id=req.item_id,
        location_id=req.location_id,
        qty=req.qty,
        batch_code=req.batch_code,
    )
