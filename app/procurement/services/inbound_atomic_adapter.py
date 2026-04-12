from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

from app.wms.inbound.contracts.inbound_atomic import InboundAtomicCreateIn
from app.wms.inbound.services.inbound_atomic_service import create_inbound_atomic


async def apply_receipt_via_atomic_inbound(
    session,
    *,
    warehouse_id: int,
    receipt_ref: str,
    occurred_at: datetime | None,
    remark: str | None,
    lines: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """
    procurement -> atomic inbound adapter（第二阶段）：

    - 一次适配整张 receipt
    - source_type 固定为 upstream
    - source_biz_type 固定为 purchase_receipt_confirm
    - source_ref 使用 receipt.ref，保持 ledger 关联稳定
    - production_date / expiry_date 由 receipt lines 作为唯一决策输入传入

    当前目标：
    - 把 receipt confirm 从“一行一个事件头”
      收口为“整张 receipt 一个统一事件头”
    """
    payload = InboundAtomicCreateIn.model_validate(
        {
            "warehouse_id": int(warehouse_id),
            "source_type": "upstream",
            "source_biz_type": "purchase_receipt_confirm",
            "source_ref": str(receipt_ref),
            "occurred_at": occurred_at,
            "remark": remark,
            "lines": [
                {
                    "item_id": int(line["item_id"]),
                    "qty": int(line["qty"]),
                    "ref_line": int(line["ref_line"]),
                    "lot_code": line.get("lot_code"),
                    "production_date": line.get("production_date"),
                    "expiry_date": line.get("expiry_date"),
                }
                for line in lines
            ],
        }
    )

    out = await create_inbound_atomic(session, payload)

    return {
        "event_id": int(out.event_id) if out.event_id is not None else None,
        "event_no": out.event_no,
        "trace_id": out.trace_id,
        "source_ref": out.source_ref,
        "rows": list(out.rows or []),
    }


__all__ = ["apply_receipt_via_atomic_inbound"]
