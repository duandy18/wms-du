# app/services/reservation_service.py
from __future__ import annotations

from typing import Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ReservationService:
    """
    预留 / 释放 / 可用量查询（不直接改 stocks）。
    - 预留幂等：ref+item+loc 在 ACTIVE 下唯一；重复 reserve 不叠加
    - 释放幂等：ACTIVE → RELEASED；重复 release 无副作用
    - 可用量读取 v_available（= on_hand - reservations.ACTIVE）
    """

    async def reserve(
        self, *, session: AsyncSession, ref: str, item_id: int, location_id: int, qty: int
    ) -> Dict:
        await session.execute(
            text(
                """
                INSERT INTO reservations(item_id, location_id, qty, ref, status)
                VALUES (:iid, :loc, :qty, :ref, 'ACTIVE')
                ON CONFLICT ON CONSTRAINT uq_reserve_idem DO NOTHING
                """
            ),
            {"iid": item_id, "loc": location_id, "qty": qty, "ref": ref},
        )
        return {"ok": True, "ref": ref, "item_id": item_id, "location_id": location_id, "qty": qty}

    async def release(
        self,
        *,
        session: AsyncSession,
        ref: str,
        item_id: Optional[int] = None,
        location_id: Optional[int] = None,
    ) -> Dict:
        cond = "ref=:ref AND status='ACTIVE'"
        params = {"ref": ref}
        if item_id is not None:
            cond += " AND item_id=:iid"
            params["iid"] = item_id
        if location_id is not None:
            cond += " AND location_id=:loc"
            params["loc"] = location_id
        await session.execute(
            text(f"UPDATE reservations SET status='RELEASED' WHERE {cond}"), params
        )
        return {"ok": True, "ref": ref}

    async def available(self, *, session: AsyncSession, item_id: int, location_id: int) -> Dict:
        # 统一从 v_available 读取聚合口径（多批次合并 + 扣 ACTIVE 预留）
        row = await session.execute(
            text(
                """
                SELECT on_hand, reserved, available
                FROM v_available
                WHERE item_id=:iid AND location_id=:loc
                """
            ),
            {"iid": item_id, "loc": location_id},
        )
        m = row.mappings().first()
        if not m:
            return {
                "item_id": item_id,
                "location_id": location_id,
                "on_hand": 0,
                "reserved": 0,
                "available": 0,
            }
        return {
            "item_id": item_id,
            "location_id": location_id,
            "on_hand": int(m["on_hand"] or 0),
            "reserved": int(m["reserved"] or 0),
            "available": int(m["available"] or 0),
        }
