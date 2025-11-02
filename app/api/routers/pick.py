# app/api/routers/pick.py
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.pick_service import PickService

router = APIRouter(prefix="/pick", tags=["pick"])


class PickIn(BaseModel):
    task_id: int = Field(..., ge=1, description="拣货任务ID")
    item_id: int = Field(..., ge=1)
    qty: int = Field(..., ge=1)
    location_id: Optional[int] = Field(None, ge=0, description="拣货位；可为 0/None 走服务侧策略")
    ref: str = Field(..., description="扫描引用/对账引用（scan_ref 或人工引用）")
    device_id: Optional[str] = None
    operator: Optional[str] = None
    # 若你要显式行号，可解开下行并在回退分支使用：
    # task_line_id: Optional[int] = None


class PickOut(BaseModel):
    task_id: int
    task_line_id: int
    item_id: int
    from_location_id: int
    picked: int
    remain: int


@router.post("", response_model=PickOut)
async def pick_commit(
    body: PickIn,
    session: AsyncSession = Depends(get_session),
):
    """
    拣货真动作：
    - 优先用 PickService.record_pick_by_context()（推荐）
    - 若服务没有 by_context，则在网关内按 {task_id,item_id} 兜底定位一条 OPEN/PARTIAL 行再调用 record_pick()
    - 并发/权限不符 → 403；数量非法/无可拣 → 409
    """
    svc = PickService()

    # 1) 首选 by_context（若存在）
    if hasattr(svc, "record_pick_by_context"):
        try:
            result = await svc.record_pick_by_context(  # type: ignore[attr-defined]
                session=session,
                task_id=body.task_id,
                item_id=body.item_id,
                qty=body.qty,
                scan_ref=body.ref,
                location_id=body.location_id or 0,
                device_id=body.device_id,
                operator=body.operator,
            )
            await session.commit()
            return PickOut(**result)
        except PermissionError as e:
            await session.rollback()
            raise HTTPException(status_code=403, detail=str(e))
        except ValueError as e:
            await session.rollback()
            raise HTTPException(status_code=409, detail=str(e))

    # 2) 回退：by_context 不可用 → 网关兜底定位一条 OPEN/PARTIAL 行
    row = (
        await session.execute(
            text(
                """
                SELECT ptl.id
                  FROM pick_task_lines ptl
                 WHERE ptl.task_id = :tid
                   AND ptl.item_id = :itm
                   AND ptl.status IN ('OPEN','PARTIAL')
                 ORDER BY ptl.id
                 LIMIT 1
                """
            ),
            {"tid": body.task_id, "itm": body.item_id},
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="no OPEN/PARTIAL line for task & item")

    tlid = int(row[0])
    try:
        result = await svc.record_pick(
            session=session,
            task_line_id=tlid,
            from_location_id=body.location_id or 0,
            item_id=body.item_id,
            qty=body.qty,
            scan_ref=body.ref,
            device_id=body.device_id,
            operator=body.operator,
        )
        await session.commit()
        return PickOut(**result)
    except PermissionError as e:
        await session.rollback()
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(e))
