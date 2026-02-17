# app/services/receive_task_commit_parts/apply_inbound_effect.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.inbound_service import InboundService
from app.services.receive_task_commit_parts.utils import norm_optional_str, safe_upc


async def apply_inbound_and_collect_effect(
    session: AsyncSession,
    *,
    inbound_svc: InboundService,
    warehouse_id: int,
    item_id: int,
    units_per_case: Optional[int],
    batch_code: Optional[str],
    production_date,
    expiry_date,
    qty_base: int,
    ref: str,
    ref_line: int,
    trace_id: Optional[str],
    sub_reason: str,
    now: datetime,
) -> Tuple[int, Dict[str, Any]]:
    """
    核算主线（底座事实）：
    - 写库存/台账：inbound_svc.receive（qty=base）
    - 返回 upc（展示/凭证需要）与 effect（用于三账一致性）

    注意：
    - effect.batch_code 必须与核算语义一致：非批次商品用 None
    """
    upc = safe_upc(units_per_case)

    await inbound_svc.receive(
        session=session,
        qty=int(qty_base),
        ref=str(ref),
        ref_line=int(ref_line),
        warehouse_id=int(warehouse_id),
        item_id=int(item_id),
        batch_code=batch_code,  # ✅ 非批次商品允许 None（库存主线）
        occurred_at=now,
        production_date=production_date,
        expiry_date=expiry_date,
        trace_id=trace_id,
        sub_reason=str(sub_reason),
    )

    bcode_opt = norm_optional_str(batch_code)
    effect: Dict[str, Any] = {
        "warehouse_id": int(warehouse_id),
        "item_id": int(item_id),
        "batch_code": bcode_opt,
        "qty": int(qty_base),
        "ref": str(ref),
        "ref_line": int(ref_line),
    }
    return int(upc), effect
