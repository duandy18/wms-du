# app/services/reservation_state.py
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def mark_consumed(session: AsyncSession, reservation_id: int) -> None:
    """
    将一张 reservation 标记为 consumed，并同步行的 consumed_qty。
    """
    now = datetime.now(timezone.utc)

    await session.execute(
        text(
            """
            UPDATE reservation_lines
               SET consumed_qty = qty,
                   updated_at   = :now
             WHERE reservation_id = :rid
            """
        ),
        {"rid": reservation_id, "now": now},
    )

    await session.execute(
        text(
            """
            UPDATE reservations
               SET status    = 'consumed',
                   updated_at = :now
             WHERE id = :rid
            """
        ),
        {"rid": reservation_id, "now": now},
    )


async def mark_released(
    session: AsyncSession,
    reservation_id: int,
    *,
    reason: str = "expired",
) -> None:
    """
    将一张 reservation 标记为“释放/过期”等终结状态。
    """
    now = datetime.now(timezone.utc)
    await session.execute(
        text(
            """
            UPDATE reservations
               SET status     = :reason,
                   updated_at = :now
             WHERE id = :rid
            """
        ),
        {"rid": reservation_id, "reason": reason, "now": now},
    )
