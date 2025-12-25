# app/services/platform_events_error_log.py
from __future__ import annotations

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event_error_log import EventErrorLog
from app.services.platform_events_extractors import extract_ref, extract_shop_id, extract_state


async def log_error_isolated(
    session: AsyncSession,
    platform: str,
    raw,
    err: Exception,
) -> None:
    msg = str(err)
    if len(msg) > 240:
        msg = msg[:240] + "…"

    try:
        async with session.begin_nested():
            await session.execute(
                insert(EventErrorLog).values(
                    platform=str(platform or ""),
                    shop_id=extract_shop_id(raw),
                    order_no=extract_ref(raw),
                    idempotency_key=f"{platform}:{extract_ref(raw)}",
                    from_state=None,
                    to_state=extract_state(raw),
                    error_code=type(err).__name__,
                    error_msg=msg,
                    payload_json=raw,
                    retry_count=0,
                    max_retries=0,
                )
            )
    except Exception:
        # 不能因为记录 error_log 失败把原错误吞掉，这里只是不再抛二次错误
        pass
