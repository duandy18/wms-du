from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class InboundTaskProbeLine:
    line_no: int
    item_id: int
    item_uom_id: int
    item_name_snapshot: str | None
    uom_name_snapshot: str | None


async def get_inbound_task_probe_lines(
    session: AsyncSession,
    *,
    receipt_no: str,
) -> list[InboundTaskProbeLine]:
    head = (
        await session.execute(
            text(
                """
                SELECT
                  id,
                  status
                FROM inbound_receipts
                WHERE receipt_no = :receipt_no
                LIMIT 1
                """
            ),
            {"receipt_no": str(receipt_no)},
        )
    ).mappings().first()

    if head is None:
        raise HTTPException(status_code=404, detail="inbound_task_not_found")

    if str(head["status"]) != "RELEASED":
        raise HTTPException(
            status_code=409,
            detail=f"inbound_task_not_released:{head['status']}",
        )

    rows = (
        await session.execute(
            text(
                """
                SELECT
                  line_no,
                  item_id,
                  item_uom_id,
                  item_name_snapshot,
                  uom_name_snapshot
                FROM inbound_receipt_lines
                WHERE inbound_receipt_id = :receipt_id
                ORDER BY line_no ASC
                """
            ),
            {"receipt_id": int(head["id"])},
        )
    ).mappings().all()

    return [
        InboundTaskProbeLine(
            line_no=int(r["line_no"]),
            item_id=int(r["item_id"]),
            item_uom_id=int(r["item_uom_id"]),
            item_name_snapshot=r["item_name_snapshot"],
            uom_name_snapshot=r["uom_name_snapshot"],
        )
        for r in rows
    ]


__all__ = [
    "InboundTaskProbeLine",
    "get_inbound_task_probe_lines",
]
