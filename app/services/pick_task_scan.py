# app/services/pick_task_scan.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pick_task_line import PickTaskLine
from app.services.pick_task_loaders import load_task

UTC = timezone.utc


# ✅ 结构化错误：服务层只负责“裁决与证据”，不负责 HTTP 形态
class PickTaskScanError(ValueError):
    def __init__(self, *, error_code: str, message: str, details: Optional[list] = None):
        super().__init__(message)
        self.error_code = str(error_code)
        self.message = str(message)
        self.details = details or []


def _calc_line_status(*, req_qty: int, picked_qty: int) -> str:
    """
    事实驱动状态（不依赖 trigger）：
    - picked <= 0        -> OPEN
    - 0 < picked < req   -> PARTIAL
    - picked >= req      -> DONE
    """
    req = int(req_qty or 0)
    picked = int(picked_qty or 0)

    if picked <= 0:
        return "OPEN"
    if req > 0 and picked < req:
        return "PARTIAL"
    # req==0（不应出现）或 picked>=req：都按 DONE（最保守）
    return "DONE"


def _can_accept_scan(task_status: str) -> bool:
    # ✅ 兼容历史/脏数据：NEW 视为可扫描（等价 READY）
    return str(task_status) in ("NEW", "READY", "ASSIGNED", "PICKING")


async def record_scan(
    session: AsyncSession,
    *,
    task_id: int,
    item_id: int,
    qty: int,
    batch_code: Optional[str],
):
    """
    扫码拣货：只更新拣货任务行（req_qty / picked_qty / batch_code / status），
    不直接动库存。库存扣减统一在 commit_ship 中完成。

    状态机（最小闭环，事实驱动）：
    - task.status: NEW/READY/ASSIGNED -> PICKING（发生任何 picked_qty>0）
    - line.status: OPEN / PARTIAL / DONE
    """
    # 兜底：路由层一般已用 schema 限制 qty>0，但这里仍保留防御式护栏
    if int(qty) == 0:
        return await load_task(session, task_id)

    task = await load_task(session, task_id, for_update=True)

    if not _can_accept_scan(task.status):
        # ✅ 结构化拒绝：前端无需猜状态含义
        raise PickTaskScanError(
            error_code="pick_task_scan_reject",
            message="当前任务状态不允许扫码拣货。",
            details=[
                {
                    "type": "guard",
                    "guard": "scan",
                    "task_id": int(task.id),
                    "status": str(task.status),
                    "allowed": ["NEW", "READY", "ASSIGNED", "PICKING"],
                    "reason": "status_not_allowed",
                }
            ],
        )

    norm_batch = (batch_code or "").strip() or None
    target: Optional[PickTaskLine] = None
    for line in task.lines or []:
        if line.item_id == item_id and ((line.batch_code or None) == norm_batch):
            target = line
            break

    now = datetime.now(UTC)

    if target is None:
        # 新增“临时事实行”（order_id=None）：req_qty 用本次 qty 作为最小基线
        picked0 = int(qty)
        req0 = int(qty)
        status0 = _calc_line_status(req_qty=req0, picked_qty=picked0)

        target = PickTaskLine(
            task_id=task.id,
            order_id=None,
            order_line_id=None,
            item_id=int(item_id),
            req_qty=req0,
            picked_qty=picked0,
            batch_code=norm_batch,
            prefer_pickface=False,
            target_location_id=None,
            status=status0,
            note="TEMP_FACT",
            created_at=now,
            updated_at=now,
        )
        session.add(target)
        await session.flush()
        task.lines.append(target)
    else:
        # 更新既有行：累加 picked_qty
        if not target.batch_code and norm_batch:
            target.batch_code = norm_batch

        target.picked_qty = int(target.picked_qty or 0) + int(qty)
        target.updated_at = now

        # ✅ 事实驱动：更新行状态
        target.status = _calc_line_status(req_qty=int(target.req_qty or 0), picked_qty=int(target.picked_qty or 0))

    # ✅ 事实驱动：任务状态推进到 PICKING（但不在 scan 阶段写 DONE）
    if task.status in ("NEW", "READY", "ASSIGNED"):
        task.status = "PICKING"
    task.updated_at = now

    await session.flush()
    return task
