from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.pick_service import PickService

router = APIRouter(prefix="/pick", tags=["pick"])


class PickIn(BaseModel):
    """
    v2 拣货请求体（与 PickService.record_pick 对齐）：

    - 必填：
        * item_id: 商品 ID
        * qty: 本次拣货数量（>0）
        * warehouse_id: 仓库 ID
        * batch_code: 扣减的批次编码
        * ref: 拣货引用（用于台账幂等，如 SCAN-xxx）
    - 可选：
        * occurred_at: 拣货时间，默认当前时间（UTC）
        * task_line_id: 若有拣货任务行，可用于后续扩展 remain 计算
        * location_id / device_id / operator: 仅作为审计/扩展信息，当前不影响扣减逻辑
    """

    item_id: int = Field(..., ge=1, description="商品 ID")
    qty: int = Field(..., ge=1, description="拣货数量")
    warehouse_id: int = Field(..., ge=1, description="仓库 ID")
    batch_code: str = Field(..., min_length=1, description="批次编码")
    ref: str = Field(..., min_length=1, description="拣货引用（如扫描号）")

    occurred_at: Optional[datetime] = Field(
        default=None, description="拣货时间（缺省为当前 UTC 时间）"
    )

    task_line_id: Optional[int] = Field(
        default=None, description="可选：拣货任务行 ID，用于后续扩展 remain 计算"
    )
    location_id: Optional[int] = Field(
        default=None, ge=0, description="拣货库位 ID（当前不参与扣减，仅作记录）"
    )
    device_id: Optional[str] = Field(default=None, description="设备 ID（扫描枪等）")
    operator: Optional[str] = Field(default=None, description="操作人 ID 或姓名")


class PickOut(BaseModel):
    """
    拣货结果（与前端展示需求对齐）：
    - picked: 本次实际扣减数量
    - stock_after: 扣减后库存余额（如果 StockService 有返回）
    - warehouse_id / batch_code / item_id: 标识拣货槽位
    - status: OK / IDEMPOTENT / ERROR
    """

    item_id: int
    warehouse_id: int
    batch_code: str
    picked: int
    stock_after: Optional[int] = None
    ref: str
    status: str


@router.post("", response_model=PickOut)
async def pick_commit(
    body: PickIn,
    session: AsyncSession = Depends(get_session),
):
    """
    拣货动作：调用 PickService.record_pick 立即扣减库存（原子 + 幂等）。

    当前版本暂不直接更新 pick_task_lines / remain，仅返回本次拣货结果；
    后续可在此基础上增加任务维度的 picked/remain 统计。
    """
    svc = PickService()

    occurred_at = body.occurred_at or datetime.now(timezone.utc)

    try:
        result = await svc.record_pick(
            session=session,
            item_id=body.item_id,
            qty=body.qty,
            ref=body.ref,
            occurred_at=occurred_at,
            batch_code=body.batch_code,
            warehouse_id=body.warehouse_id,
            task_line_id=body.task_line_id,
        )
        await session.commit()
    except ValueError as e:
        # 典型业务错误（库存不足 / 批次不合法等）
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    except Exception:
        await session.rollback()
        raise

    return PickOut(
        item_id=body.item_id,
        warehouse_id=result.get("warehouse_id", body.warehouse_id),
        batch_code=result.get("batch_code", body.batch_code),
        picked=result.get("picked", body.qty),
        stock_after=result.get("stock_after"),
        ref=result.get("ref", body.ref),
        status=result.get("status", "OK"),
    )
