# app/services/audit_writer_sync.py
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("wmsdu.audit")


class SyncAuditEventWriter:
    """
    同步版审计写入器（用于同步 Session 的路由，如 shipping-quote/calc/recommend）。

    语义与 AuditEventWriter 一致：
    - category = flow
    - meta 至少包含 flow/event
    """

    @staticmethod
    def write(
        session: Session,
        *,
        flow: str,
        event: str,
        ref: str,
        trace_id: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        auto_commit: bool = False,
    ) -> None:
        payload: Dict[str, Any] = dict(meta or {})
        payload.setdefault("flow", flow)
        payload.setdefault("event", event)
        if trace_id:
            payload.setdefault("trace_id", trace_id)

        try:
            session.execute(
                text(
                    """
                    INSERT INTO audit_events (category, ref, meta, trace_id, created_at)
                    VALUES (
                        :category,
                        :ref,
                        CAST(:meta AS jsonb),
                        :trace_id,
                        now()
                    )
                    """
                ),
                {
                    "category": flow,
                    "ref": ref,
                    "meta": json.dumps(payload, ensure_ascii=False),
                    "trace_id": trace_id,
                },
            )
            if auto_commit:
                session.commit()
        except Exception as e:
            logger.debug("audit_events insert failed: %s", e)
            logger.info(
                "[audit-fallback] %s | %s | %s",
                flow,
                ref,
                json.dumps(payload, ensure_ascii=False),
            )
