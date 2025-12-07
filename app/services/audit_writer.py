# app/services/audit_writer.py
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("wmsdu.audit")


class AuditEventWriter:
    """
    统一审计写入器：

    - 唯一职责：往 audit_events 表写一行。
    - 语义约定：
        * category = flow
        * ref      = 业务引用（订单号 / reservation ref / ship ref 等）
        * meta     = jsonb，至少包含：
            - flow
            - event
          其余字段任意扩展（platform / shop_id / warehouse_id / reason ...）
        * trace_id = 链路 ID，用于 TraceService 聚合。
    """

    @staticmethod
    async def write(
        session: AsyncSession,
        *,
        flow: str,
        event: str,
        ref: str,
        trace_id: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        auto_commit: bool = False,
    ) -> None:
        """
        写入一条 audit_events 记录。

        参数：
          - flow:   流程大类，例如 "OUTBOUND" / "INBOUND" / "SCAN"
          - event:  具体事件，例如 "ORDER_CREATED" / "SHIP_COMMIT"
          - ref:    业务引用
          - trace_id: 链路 ID（可选）
          - meta:    附加字段，会并入 meta json
          - auto_commit: 是否自动提交事务（默认为 False）
        """
        payload: Dict[str, Any] = dict(meta or {})

        # 尽量保证 meta 内一定有 flow / event / trace_id（如未显式给则补充）
        payload.setdefault("flow", flow)
        payload.setdefault("event", event)
        if trace_id:
            payload.setdefault("trace_id", trace_id)

        try:
            await session.execute(
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
                await session.commit()
        except Exception as e:
            # 不让审计写入影响主流程，统一打 DEBUG + INFO 兜底
            logger.debug("audit_events insert failed: %s", e)
            logger.info(
                "[audit-fallback] %s | %s | %s",
                flow,
                ref,
                json.dumps(payload, ensure_ascii=False),
            )


# ------------------------------------------------------------------------------
# 兼容层：保留一个简单的 AuditService，供旧代码迁移时使用
# ------------------------------------------------------------------------------


class AuditService:
    """
    兼容用审计服务（薄封装）：

    - 新代码请直接用 AuditEventWriter.write；
    - 旧代码如依赖 AuditService，可以逐步迁移。
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log_event(
        self,
        *,
        flow: str,
        event: str,
        ref: str,
        trace_id: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        auto_commit: bool = False,
    ) -> None:
        await AuditEventWriter.write(
            self.session,
            flow=flow,
            event=event,
            ref=ref,
            trace_id=trace_id,
            meta=meta,
            auto_commit=auto_commit,
        )
