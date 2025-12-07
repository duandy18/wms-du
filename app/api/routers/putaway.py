# app/api/routers/putaway.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException

# 兼容历史路径：/putaway
router = APIRouter(prefix="/putaway", tags=["putaway"])

DEPRECATE_MSG = (
    "Putaway/Transfer has been deprecated in Phase 2.8+. "
    "Use INBOUND (receive), OUTBOUND (ship), and COUNT (adjust). "
    "For moves, perform a net-zero two-step adjust between source and target warehouses."
)


@router.post("")
async def putaway_compat():
    # 统一返回 410 Gone，并给出迁移说明
    raise HTTPException(status_code=410, detail=DEPRECATE_MSG)


# 有些旧用例/客户端可能命中 /putaway/move
@router.post("/move")
async def putaway_move_compat():
    raise HTTPException(status_code=410, detail=DEPRECATE_MSG)
