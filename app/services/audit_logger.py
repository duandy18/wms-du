# app/services/audit_logger.py
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("wmsdu.audit")


async def log_event_db(
    session: Optional[AsyncSession],
    *,
    kind: str,
    key: str,
    extra: dict[str, Any] | None = None,
) -> None:
    """
    尝试将审计事件落库（存在 event_audit_log 表时生效）。
    表结构建议（不强依赖）：
      event_audit_log(kind text, key text, payload jsonb, occurred_at timestamptz)
      索引： (kind), (occurred_at desc)
    """
    if session is None:
        return
    try:
        await session.execute(
            text(
                """
                INSERT INTO event_audit_log(kind, key, payload, occurred_at)
                VALUES (:k, :key, :payload, :ts)
                """
            ),
            {
                "k": kind,
                "key": key,
                "payload": json.dumps(extra or {}, ensure_ascii=False),
                "ts": datetime.now(UTC),
            },
        )
    except Exception as e:
        # 不让审计失败影响主流程
        logger.debug("audit log insert skipped: %s", e)


def log_event(kind: str, key: str, extra: dict[str, Any] | None = None) -> None:
    """
    轻量审计（本地日志）。数据库落表由调用方按需协程调用 log_event_db。
    """
    try:
        logger.info("[audit] %s | %s | %s", kind, key, json.dumps(extra or {}, ensure_ascii=False))
    except Exception:
        # 不要让日志格式化抛错
        logger.info("[audit] %s | %s", kind, key)
