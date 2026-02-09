# app/services/platform_order_manual_decisions_service.py
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ManualDecisionRow:
    platform: str
    store_id: int
    ext_order_no: str
    order_id: Optional[int]

    line_key: Optional[str]
    line_no: Optional[int]
    platform_sku_id: Optional[str]
    fact_qty: Optional[int]

    item_id: int
    qty: int
    note: Optional[str]

    manual_reason: Optional[str]
    risk_flags: Optional[list[str]]


def new_batch_id() -> UUID:
    return uuid4()


async def insert_manual_decisions_batch(
    *,
    session: AsyncSession,
    batch_id: UUID,
    rows: Iterable[ManualDecisionRow],
) -> int:
    """
    Insert a batch of manual decision facts.
    MUST be called inside the same transaction as confirm-and-create.
    """
    sql = text(
        """
        INSERT INTO platform_order_manual_decisions(
          batch_id,
          platform, store_id, ext_order_no, order_id,
          line_key, line_no, platform_sku_id, fact_qty,
          item_id, qty, note,
          manual_reason, risk_flags,
          created_at
        )
        VALUES (
          :batch_id,
          :platform, :store_id, :ext_order_no, :order_id,
          :line_key, :line_no, :platform_sku_id, :fact_qty,
          :item_id, :qty, :note,
          :manual_reason, CAST(:risk_flags AS jsonb),
          :created_at
        )
        """
    )

    created_at = datetime.now(timezone.utc)

    payload: list[dict[str, Any]] = []
    for r in rows:
        risk_flags_json = json.dumps(r.risk_flags or [], ensure_ascii=False)
        payload.append(
            {
                "batch_id": str(batch_id),
                "platform": (r.platform or "").strip().upper(),
                "store_id": int(r.store_id),
                "ext_order_no": str(r.ext_order_no),
                "order_id": r.order_id,
                "line_key": r.line_key,
                "line_no": r.line_no,
                "platform_sku_id": r.platform_sku_id,
                "fact_qty": r.fact_qty,
                "item_id": int(r.item_id),
                "qty": int(r.qty),
                "note": r.note,
                "manual_reason": r.manual_reason,
                "risk_flags": risk_flags_json,
                "created_at": created_at,
            }
        )

    if not payload:
        return 0

    await session.execute(sql, payload)
    return len(payload)
