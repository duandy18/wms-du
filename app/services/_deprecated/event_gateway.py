# app/services/event_gateway.py
from __future__ import annotations

import json
from typing import Any, Optional, Set, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.events_enums import ErrorCode, EventState
from app.metrics import ERRS

# ============================================================
#                v1.0 强契约：固定列名 & 明确语义
# （与现有实现一致）
# ============================================================

ALLOWED: Set[Tuple[Optional[EventState], EventState]] = {
    (None, EventState.PAID),
    (EventState.PAID, EventState.ALLOCATED),
    (EventState.ALLOCATED, EventState.SHIPPED),
    (None, EventState.VOID),
    (EventState.PAID, EventState.VOID),
    (EventState.ALLOCATED, EventState.VOID),
    (EventState.SHIPPED, EventState.VOID),
}


def _as_state(value: Optional[str | EventState]) -> Optional[EventState]:
    if value is None:
        return None
    if isinstance(value, EventState):
        return value
    if isinstance(value, str) and value.strip().lower() in {"", "none", "null"}:
        return None
    try:
        return EventState(value)
    except Exception:
        return None


async def _insert_event_error_log(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    order_no: str,
    idem_key: str,
    from_state: Optional[str],
    to_state: str,
    payload: dict[str, Any],
) -> None:
    sql = text(
        """
        INSERT INTO event_error_log (
            platform, shop_id, order_no, idempotency_key,
            from_state, to_state, retry_count, max_retries,
            error_code, error_msg, payload_json, next_retry_at
        ) VALUES (
            :platform, :shop_id, :order_no, :idem,
            :from_state, :to_state, 0, 0,
            :ecode, :emsg, :payload_json, NULL
        )
    """
    )
    await session.execute(
        sql,
        {
            "platform": platform,
            "shop_id": shop_id,
            "order_no": order_no,
            "idem": idem_key,
            "from_state": from_state,
            "to_state": to_state,
            "ecode": ErrorCode.ILLEGAL_TRANSITION.value,
            "emsg": "Transition not allowed",
            "payload_json": json.dumps(payload or {}, ensure_ascii=False),
        },
    )


async def _get_snapshot_state(
    session: AsyncSession, platform: str, shop_id: str, order_no: str
) -> Optional[str]:
    q = text(
        """
        SELECT state FROM order_state_snapshot
        WHERE platform=:p AND shop_id=:s AND order_no=:o
        LIMIT 1
    """
    )
    row = (await session.execute(q, {"p": platform, "s": shop_id, "o": order_no})).first()
    return row[0] if row else None


async def _upsert_snapshot_state(
    session: AsyncSession, platform: str, shop_id: str, order_no: str, state: str
) -> None:
    sql = text(
        """
        INSERT INTO order_state_snapshot (platform, shop_id, order_no, state, updated_at)
        VALUES (:p, :s, :o, :st, CURRENT_TIMESTAMP)
        ON CONFLICT (platform, shop_id, order_no)
        DO UPDATE SET state=EXCLUDED.state, updated_at=CURRENT_TIMESTAMP
    """
    )
    await session.execute(sql, {"p": platform, "s": shop_id, "o": order_no, "st": state})


async def enforce_transition(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    order_no: str,
    idem_key: str,
    from_state: Optional[str | EventState],
    to_state: str | EventState,
    payload: dict[str, Any],
) -> None:
    s_from = _as_state(from_state)
    s_to = _as_state(to_state)
    if s_from is None:
        snap = await _get_snapshot_state(session, platform, shop_id, order_no)
        if isinstance(snap, str):
            s_from = _as_state(snap)

    if s_to is None or (s_from, s_to) not in ALLOWED:
        await _insert_event_error_log(
            session,
            platform=platform,
            shop_id=shop_id,
            order_no=order_no,
            idem_key=idem_key,
            from_state=(
                s_from.value
                if isinstance(s_from, EventState)
                else (from_state if from_state is not None else None)
            ),
            to_state=(s_to.value if isinstance(s_to, EventState) else str(to_state)),
            payload=payload,
        )
        ERRS.labels(platform, shop_id, ErrorCode.ILLEGAL_TRANSITION.value).inc()
        raise ValueError("ILLEGAL_TRANSITION")

    await _upsert_snapshot_state(
        session,
        platform=platform,
        shop_id=shop_id,
        order_no=order_no,
        state=(s_to.value if isinstance(s_to, EventState) else str(to_state)),
    )
    return
