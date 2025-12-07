from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, constr

from app.services import reservation_lock as lock_svc
from app.services import reservation_release as release_svc

# 说明：
# - 路由聚合在 app/api/router.py 中完成，这里只提供 /reserve 子路由
# - 服务层依赖遵循你现有的 ReservationService 接口
from app.services.reservation_service import ReservationError, ReservationService

router = APIRouter(prefix="/reserve", tags=["reserve"])

# ---------- Pydantic Schemas ----------

PlatformStr = constr(strip_whitespace=True, min_length=1)
ShopIdStr = constr(strip_whitespace=True, min_length=1)
RefStr = constr(strip_whitespace=True, min_length=1)


class ReserveLockRequest(BaseModel):
    platform: PlatformStr = Field(..., description="平台代码，如 PDD/JD/TEST")
    shop_id: ShopIdStr = Field(..., description="店铺标识")
    ref: RefStr = Field(..., description="业务引用号（幂等键的一部分）")
    mode: Optional[str] = Field(
        default="DEFAULT",
        description="分配策略：DEFAULT | FEFO（按批次过期时间升序）",
    )
    occurred_at: Optional[datetime] = Field(
        default=None,
        description="业务发生时间（可选；不传则服务端填充当前时间）",
    )


class ReserveReleaseRequest(BaseModel):
    platform: PlatformStr
    shop_id: ShopIdStr
    ref: RefStr
    occurred_at: Optional[datetime] = None


class ReserveActionResponse(BaseModel):
    ok: bool
    idempotent: bool
    data: dict[str, Any]


# ---------- Helpers ----------


def _mk_response(payload: dict[str, Any]) -> ReserveActionResponse:
    """
    将服务层标准返回（包含 'status' 字段）统一转换为 API 语义：
      ok = status == 'OK'
      idempotent = status == 'IDEMPOTENT'
      data = 其余所有字段
    """
    status = str(payload.get("status", "")).upper()
    data = {k: v for k, v in payload.items() if k != "status"}
    return ReserveActionResponse(
        ok=(status == "OK"), idempotent=(status == "IDEMPOTENT"), data=data
    )


# ---------- Routes ----------


@router.post("/lock", response_model=ReserveActionResponse)
async def reserve_lock(
    body: ReserveLockRequest,
    svc: ReservationService = Depends(ReservationService.dep),
):
    """
    锁定库存（强一致 + 可选 FEFO）。
    幂等：若 Reservation 头状态非 PLANNED，返回 idempotent=true。
    失败：返回 409（例如库存不足、事务冲突等）。
    """
    try:
        result = await lock_svc.lock(
            svc.session,
            platform=body.platform,
            shop_id=body.shop_id,
            ref=body.ref,
            occurred_at=body.occurred_at,
            mode=(body.mode or "DEFAULT"),
        )
        return _mk_response(result)
    except (ReservationError, ValueError) as e:
        # 业务/一致性错误：409
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:
        # 非预期异常：500（保留最小信息）
        raise HTTPException(status_code=500, detail="LOCK_FAILED") from e


@router.post("/release", response_model=ReserveActionResponse)
async def reserve_release(
    body: ReserveReleaseRequest,
    svc: ReservationService = Depends(ReservationService.dep),
):
    """
    原路归还（严格依据 reservation_allocations 台账）。
    幂等：若 Reservation 头状态非 LOCKED，返回 idempotent=true。
    """
    try:
        result = await release_svc.release(
            svc.session,
            platform=body.platform,
            shop_id=body.shop_id,
            ref=body.ref,
            occurred_at=body.occurred_at,
        )
        return _mk_response(result)
    except (ReservationError, ValueError) as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="RELEASE_FAILED") from e
