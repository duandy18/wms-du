# app/services/event_gateway.py
from __future__ import annotations

import json
from typing import Any, Optional, Set, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.events_enums import EventState, ErrorCode
from app.metrics import ERRS

# ============================================================
#                v1.0 强契约：固定列名 & 明确语义
# 约定的表结构（必须存在以下列，避免运行时探测/分支）：
# - event_error_log(
#     platform, shop_id, order_no, idempotency_key,
#     from_state, to_state, retry_count, max_retries,
#     error_code, error_msg, payload_json, next_retry_at NULL
#   )
# - order_state_snapshot(platform, shop_id, order_no, state, updated_at)
# ============================================================

# 允许的状态迁移（单调前进 + 任意阶段可取消）
ALLOWED: Set[Tuple[Optional[EventState], EventState]] = {
    (None,                 EventState.PAID),        # initial → PAID
    (EventState.PAID,      EventState.ALLOCATED),
    (EventState.ALLOCATED, EventState.SHIPPED),
    (None,                 EventState.VOID),        # initial → VOID（可保留）
    (EventState.PAID,      EventState.VOID),
    (EventState.ALLOCATED, EventState.VOID),
    (EventState.SHIPPED,   EventState.VOID),
}


def _as_state(value: Optional[str | EventState]) -> Optional[EventState]:
    """将字符串/枚举安全转换为 EventState；非法值返回 None。"""
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


# -------------------------- 错误落表（固定列） --------------------------

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
    """
    强约束版：不再探测列名，统一写固定字段。
    - error_code 采用 ErrorCode.ILLEGAL_TRANSITION
    - error_msg 固定文案 + 负载写入 payload_json（JSON 字符串）
    - next_retry_at 置 NULL（让上层调度器按需回填）
    """
    sql = text("""
        INSERT INTO event_error_log (
            platform, shop_id, order_no, idempotency_key,
            from_state, to_state, retry_count, max_retries,
            error_code, error_msg, payload_json, next_retry_at
        ) VALUES (
            :platform, :shop_id, :order_no, :idem,
            :from_state, :to_state, 0, 0,
            :ecode, :emsg, :payload_json, NULL
        )
    """)
    await session.execute(sql, {
        "platform": platform,
        "shop_id": shop_id,
        "order_no": order_no,
        "idem": idem_key,
        "from_state": from_state,
        "to_state": to_state,
        "ecode": ErrorCode.ILLEGAL_TRANSITION.value,
        "emsg": "Transition not allowed",
        "payload_json": json.dumps(payload or {}, ensure_ascii=False),
    })


# -------------------------- 快照：读取 & 写回 --------------------------

async def _get_snapshot_state(
    session: AsyncSession, platform: str, shop_id: str, order_no: str
) -> Optional[str]:
    q = text("""
        SELECT state FROM order_state_snapshot
        WHERE platform=:p AND shop_id=:s AND order_no=:o
        LIMIT 1
    """)
    row = (await session.execute(q, {"p": platform, "s": shop_id, "o": order_no})).first()
    return row[0] if row else None


async def _upsert_snapshot_state(
    session: AsyncSession, platform: str, shop_id: str, order_no: str, state: str
) -> None:
    # PG/SQLite 统一 UPSERT（依赖 (platform,shop_id,order_no) 唯一）
    sql = text("""
        INSERT INTO order_state_snapshot (platform, shop_id, order_no, state, updated_at)
        VALUES (:p, :s, :o, :st, CURRENT_TIMESTAMP)
        ON CONFLICT (platform, shop_id, order_no)
        DO UPDATE SET state=EXCLUDED.state, updated_at=CURRENT_TIMESTAMP
    """)
    await session.execute(sql, {"p": platform, "s": shop_id, "o": order_no, "st": state})


# -------------------------- 状态机守卫主函数 --------------------------

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
    """
    事件状态机守卫（强契约版）：
      - (from → to) 不在 ALLOWED：写入 event_error_log、ERRS 计数 ILLEGAL_TRANSITION，并抛异常
      - 合法：写回快照，交由上层继续推进（记账/出库等）
    """
    s_from = _as_state(from_state)
    s_to   = _as_state(to_state)

    # 若未提供 from_state，则尝试从快照补齐
    if s_from is None:
        snap = await _get_snapshot_state(session, platform, shop_id, order_no)
        if isinstance(snap, str):
            s_from = _as_state(snap)

    # 非法迁移：落错 + 计数 + 抛异常
    if s_to is None or (s_from, s_to) not in ALLOWED:
        await _insert_event_error_log(
            session,
            platform=platform,
            shop_id=shop_id,
            order_no=order_no,
            idem_key=idem_key,
            from_state=(s_from.value if isinstance(s_from, EventState) else (from_state if from_state is not None else None)),
            to_state=(s_to.value if isinstance(s_to, EventState) else str(to_state)),
            payload=payload,
        )
        ERRS.labels(platform, shop_id, ErrorCode.ILLEGAL_TRANSITION.value).inc()
        raise ValueError("ILLEGAL_TRANSITION")

    # 合法迁移：更新快照
    await _upsert_snapshot_state(
        session,
        platform=platform,
        shop_id=shop_id,
        order_no=order_no,
        state=(s_to.value if isinstance(s_to, EventState) else str(to_state)),
    )
    return
