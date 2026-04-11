from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.wms.inbound.contracts.inbound_atomic import InboundAtomicCreateIn
from app.wms.inbound.services.inbound_atomic_service import create_inbound_atomic


async def apply_receipt_line_via_atomic_inbound(
    session,
    *,
    warehouse_id: int,
    receipt_ref: str,
    ref_line: int,
    occurred_at: datetime | None,
    item_id: int,
    qty_base: int,
    lot_code: str | None,
    production_date: date | None,
    expiry_date: date | None,
) -> dict[str, Any]:
    """
    procurement -> atomic inbound adapter（第一阶段）：

    - 一次只适配一条 receipt line
    - source_type 固定为 upstream
    - source_biz_type 固定为 purchase_receipt_confirm
    - source_ref 使用 receipt.ref，保持 ledger 关联稳定
    - production_date / expiry_date 由 receipt line 作为唯一决策输入传入
    """
    _ = occurred_at

    payload = InboundAtomicCreateIn.model_validate(
        {
            "warehouse_id": int(warehouse_id),
            "source_type": "upstream",
            "source_biz_type": "purchase_receipt_confirm",
            "source_ref": str(receipt_ref),
            "lines": [
                {
                    "item_id": int(item_id),
                    "qty": int(qty_base),
                    "ref_line": int(ref_line),
                    "lot_code": lot_code,
                    "production_date": production_date,
                    "expiry_date": expiry_date,
                }
            ],
        }
    )

    out = await create_inbound_atomic(session, payload)

    row = out.rows[0] if out.rows else None
    return {
        "trace_id": out.trace_id,
        "source_ref": out.source_ref,
        "row": row,
    }


__all__ = ["apply_receipt_line_via_atomic_inbound"]
