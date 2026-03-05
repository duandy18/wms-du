# app/services/audit_logger.py
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("wmsdu.audit")


class AuditLogger:
    """
    通用审计记录器。
    所有服务层（如 Outbound、Inbound 等）均通过该类写入 audit_events。
    """

    @staticmethod
    async def log(
        session: Optional[AsyncSession],
        *,
        category: str,
        ref: str,
        meta: dict[str, Any] | None = None,
        trace_id: Optional[str] = None,
    ) -> None:
        """
        尝试将审计事件落库；如表不存在则仅打印日志。
        表结构建议：
          audit_events(
            id bigserial primary key,
            category varchar,
            ref varchar,
            meta jsonb,
            trace_id varchar(64),
            created_at timestamptz default now()
          )

        trace_id：
          - 会被附加到 meta 中（meta.trace_id）；
          - 同时写入 audit_events.trace_id 列，便于 trace 聚合。
        """
        if session is None:
            logger.warning("[audit] no session provided; event=%s ref=%s", category, ref)
            return

        payload = dict(meta or {})
        if trace_id:
            payload.setdefault("trace_id", trace_id)

        try:
            await session.execute(
                text(
                    """
                    INSERT INTO audit_events (category, ref, meta, trace_id, created_at)
                    VALUES (:c, :r, CAST(:m AS jsonb), :tid, now())
                    """
                ),
                {
                    "c": category,
                    "r": ref,
                    "m": json.dumps(payload, ensure_ascii=False),
                    "tid": trace_id,
                },
            )
            await session.commit()
            logger.info(
                "[audit] %s | %s | %s", category, ref, json.dumps(payload, ensure_ascii=False)
            )
        except Exception as e:
            logger.debug("audit log insert skipped: %s", e)
            logger.info(
                "[audit-fallback] %s | %s | %s",
                category,
                ref,
                json.dumps(payload, ensure_ascii=False),
            )


# ----------------------------------------------------------------------
# 向后兼容：提供旧函数接口 (log_event_db / log_event)
# ----------------------------------------------------------------------


async def log_event_db(
    session: Optional[AsyncSession],
    *,
    kind: str,
    key: str,
    extra: dict[str, Any] | None = None,
    trace_id: Optional[str] = None,
) -> None:
    """兼容旧接口"""
    await AuditLogger.log(session, category=kind, ref=key, meta=extra or {}, trace_id=trace_id)


def log_event(kind: str, key: str, extra: dict[str, Any] | None = None) -> None:
    """轻量日志接口（无 DB，会直接打日志）"""
    try:
        logger.info("[audit] %s | %s | %s", kind, key, json.dumps(extra or {}, ensure_ascii=False))
    except Exception:
        logger.info("[audit] %s | %s", kind, key)
