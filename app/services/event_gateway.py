# app/services/event_gateway.py
from __future__ import annotations

import json
from typing import Any, Optional, Set, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.events_enums import EventState, ErrorCode
from app.metrics import ERRS

# 允许的状态迁移（单调前进 + 任意阶段可取消）
ALLOWED: Set[Tuple[Optional[EventState], EventState]] = {
    (None,                 EventState.PAID),        # initial → PAID
    (None,                 EventState.ALLOCATED),   # initial → ALLOCATED
    (EventState.PAID,      EventState.ALLOCATED),
    (EventState.ALLOCATED, EventState.SHIPPED),
    (None,                 EventState.VOID),        # initial → VOID（保留）
    (EventState.PAID,      EventState.VOID),
    (EventState.ALLOCATED, EventState.VOID),
    (EventState.SHIPPED,   EventState.VOID),
}

# 首次落地允许（字符串兜底，避免枚举不一致导致误杀）
INITIAL_ALLOWED_STR = {"PAID", "ALLOCATED"}


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


# ---------- 运行时探测表结构（兼容新旧列名） ----------
_EVENT_ERROR_LOG_COLS: Optional[Set[str]] = None


async def _get_event_error_log_cols(session: AsyncSession) -> Set[str]:
    global _EVENT_ERROR_LOG_COLS
    if _EVENT_ERROR_LOG_COLS is not None:
        return _EVENT_ERROR_LOG_COLS
    q = text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='event_error_log'"
    )
    rows = (await session.execute(q)).all()
    _EVENT_ERROR_LOG_COLS = {r[0] for r in rows}
    return _EVENT_ERROR_LOG_COLS


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
    动态判断实际存在的列，拼接 INSERT，兼容如下旧/新字段：
      - 错误码：error_code / error_type
      - 错误消息：error_msg / message
      - 负载：payload_json / payload（统一 json.dumps）
      - next_retry_at（可选）
    """
    cols = await _get_event_error_log_cols(session)

    insert_cols = [
        "platform", "shop_id", "order_no", "idempotency_key",
        "from_state", "to_state", "retry_count", "max_retries"
    ]
    params = {
        "platform": platform,
        "shop_id": shop_id,
        "order_no": order_no,
        "idempotency_key": idem_key,
        "from_state": from_state,
        "to_state": to_state,
        "retry_count": 0,
        "max_retries": 0,
    }

    wrote_code = False
    if "error_code" in cols:
        insert_cols.append("error_code")
        params["error_code"] = ErrorCode.ILLEGAL_TRANSITION.value
        wrote_code = True
    if "error_type" in cols:
        insert_cols.append("error_type")
        params["error_type"] = (
            ErrorCode.ILLEGAL_TRANSITION.value if not wrote_code else params["error_code"]
        )

    if "error_msg" in cols:
        insert_cols.append("error_msg")
        params["error_msg"] = "Transition not allowed"
    elif "message" in cols:
        insert_cols.append("message")
        params["message"] = "Transition not allowed"

    payload_str = json.dumps(payload or {}, ensure_ascii=False)
    if "payload_json" in cols:
        insert_cols.append("payload_json")
        params["payload_json"] = payload_str
    elif "payload" in cols:
        insert_cols.append("payload")
        params["payload"] = payload_str

    if "next_retry_at" in cols:
        insert_cols.append("next_retry_at")
        params["next_retry_at"] = None

    sql = (
        "INSERT INTO event_error_log (" + ", ".join(insert_cols) + ") "
        "VALUES (" + ", ".join(f":{c}" for c in insert_cols) + ")"
    )
    await session.execute(text(sql), params)


# ---------- 快照：读取 & 写回 ----------
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
    sql = text("""
        INSERT INTO order_state_snapshot(platform, shop_id, order_no, state, updated_at)
        VALUES (:p, :s, :o, :st, CURRENT_TIMESTAMP)
        ON CONFLICT (platform, shop_id, order_no)
        DO UPDATE SET state=EXCLUDED.state, updated_at=CURRENT_TIMESTAMP
    """)
    await session.execute(sql, {"p": platform, "s": shop_id, "o": order_no, "st": state})


# ---------- 状态机守卫主函数 ----------
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
    事件状态机守卫：
      - 若 (from_state → to_state) 不在 ALLOWED，写入 event_error_log，错误计数，并抛异常。
      - 合法则写回快照，交由上层继续业务推进。
    """
    # 目标态字符串（兜底大小写）
    t_str = (to_state.value if isinstance(to_state, EventState) else str(to_state or "")).upper()

    # ★★ 1) 显式传入 from_state 为 None → 直接放行到初始态（不回填快照）
    if (from_state is None) and (t_str in INITIAL_ALLOWED_STR):
        await _upsert_snapshot_state(session, platform=platform, shop_id=shop_id, order_no=order_no, state=t_str)
        return

    # 2) 之后才尝试把非空 from_state 统一到枚举；若仍是 None，再尝试从快照补齐
    s_from = _as_state(from_state)
    s_to   = _as_state(to_state)

    if s_from is None:
        snap = await _get_snapshot_state(session, platform, shop_id, order_no)
        if isinstance(snap, str):
            s_from = _as_state(snap)

    # 3) 如果还是首次（没有历史），并且目标在初始集合，也放行（双保险）
    if (s_from is None) and (t_str in INITIAL_ALLOWED_STR):
        await _upsert_snapshot_state(session, platform=platform, shop_id=shop_id, order_no=order_no, state=t_str)
        return

    # 4) 常规校验（基于枚举）
    if s_to is None or (s_from, s_to) not in ALLOWED:
        await _insert_event_error_log(
            session,
            platform=platform,
            shop_id=shop_id,
            order_no=order_no,
            idem_key=idem_key,
            from_state=(s_from.value if isinstance(s_from, EventState) else (from_state if from_state is not None else None)),
            to_state=t_str or (s_to.value if isinstance(s_to, EventState) else "UNKNOWN"),
            payload=payload,
        )
        ERRS.labels(platform, shop_id, ErrorCode.ILLEGAL_TRANSITION.value).inc()
        raise ValueError("ILLEGAL_TRANSITION")

    # 5) 合法迁移：更新快照
    await _upsert_snapshot_state(
        session,
        platform=platform,
        shop_id=shop_id,
        order_no=order_no,
        state=(s_to.value if isinstance(s_to, EventState) else t_str),
    )
    return
