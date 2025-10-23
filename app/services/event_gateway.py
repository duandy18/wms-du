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
      - 错误码：error_code / error_type (NOT NULL 兼容)
      - 错误消息：error_msg / message
      - 负载：payload_json / payload（以 JSON 字符串形式写入，避免 psycopg3 适配错误）
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

    # 错误码：优先 error_code；若存在 error_type 也一并写（应对 NOT NULL）
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

    # 错误消息：优先 error_msg，否则 message
    if "error_msg" in cols:
        insert_cols.append("error_msg")
        params["error_msg"] = "Transition not allowed"
    elif "message" in cols:
        insert_cols.append("message")
        params["message"] = "Transition not allowed"

    # 负载：优先 payload_json，否则 payload（统一 json.dumps）
    payload_str = json.dumps(payload or {}, ensure_ascii=False)
    if "payload_json" in cols:
        insert_cols.append("payload_json")
        params["payload_json"] = payload_str
    elif "payload" in cols:
        insert_cols.append("payload")
        params["payload"] = payload_str

    # next_retry_at（可选）
    if "next_retry_at" in cols:
        insert_cols.append("next_retry_at")
        params["next_retry_at"] = None

    sql = (
        "INSERT INTO event_error_log (" + ", ".join(insert_cols) + ") "
        "VALUES (" + ", ".join(f":{c}" for c in insert_cols) + ")"
    )
    await session.execute(text(sql), params)


# ---------- 快照：读取 & 写回（自动识别当前状态） ----------
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
    # PG / SQLite 统一 ON CONFLICT upsert（依赖 (platform,shop_id,order_no) 唯一）
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
      - 如果 (from_state → to_state) 不在 ALLOWED，写入 event_error_log（兼容新旧 schema），ERRS 计数 ILLEGAL_TRANSITION，并抛异常。
      - 合法则不做任何变更，由上层继续业务推进，并写回快照用于下一跳自动识别。
    """
    s_from = _as_state(from_state)
    s_to   = _as_state(to_state)

    # 若调用方未提供 from_state，则尝试从快照补齐
    if s_from is None:
        snap = await _get_snapshot_state(session, platform, shop_id, order_no)
        if isinstance(snap, str):
            s_from = _as_state(snap)

    # 非法：落错 + 计数 + 抛异常
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

    # 合法：写回/更新快照，下次可不带 from_state
    await _upsert_snapshot_state(
        session,
        platform=platform,
        shop_id=shop_id,
        order_no=order_no,
        state=(s_to.value if isinstance(s_to, EventState) else str(to_state)),
    )
    # 合法迁移到此结束：交由上层继续推进（记账/出库等）
    return
