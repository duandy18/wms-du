# app/core/audit.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.services._event_writer import EventWriter

# ---------------- Trace Context ----------------


@dataclass
class TraceContext:
    """
    轻量级 Trace 上下文：

    - trace_id: 全局唯一字符串（UUID4）
    - source: 可选，记录生成来源（例如 'http:/orders', 'platform:PDD:PAID'）
    """

    trace_id: str
    source: Optional[str] = None


def new_trace(source: str) -> TraceContext:
    """为一次操作生成新的 TraceContext。"""
    return TraceContext(trace_id=uuid4().hex, source=source)


def ensure_trace(ctx: Optional[TraceContext], source: str) -> TraceContext:
    """若已有 TraceContext 则用之，否则生成新的。"""
    return ctx if ctx is not None else new_trace(source)


# ---------------- Scan 专用 AuditWriter ----------------


class AuditWriter:
    """
    统一事件写入口径（Scan 专用）：

    - probe/other: message=纯字符串（scan_ref），写入 event_log
    - commit/error/path: message=对象，写入 event_log
    - ★ 新增：同时写入 event_store，payload 中保留原始 message，并带上 trace_id=scan_ref

    事件源名严格固定为 scan_<mode>_<action>，以匹配测试断言。
    """

    @staticmethod
    async def _write(
        session: AsyncSession,
        source: str,
        level: str,
        message: Any,
    ) -> int:
        """
        写入 event_log（保持原行为）+ event_store（带 trace_id），
        其中：
        - trace_id 自动从 message 中推导：
            * 如果 message 是 str 且以 'scan:' 开头 → trace_id=message
            * 如果 message 是 Mapping，优先使用 message['dedup'] 作为 trace_id
        """
        # 1) 原行为：写入 event_log
        writer = EventWriter(source)
        ev = await writer.write_json(session, level=level, message=message)

        # 2) 额外：写入 event_store 供 TraceService 使用（非强制）
        trace_id: Optional[str] = None
        payload_for_store: Any = message

        # 从 message 中推导 trace_id
        if isinstance(message, str):
            # probe/other: message = scan_ref
            if message.startswith("scan:"):
                trace_id = message
                payload_for_store = {"dedup": message}
        elif isinstance(message, Mapping):
            dedup = message.get("dedup")
            if isinstance(dedup, str) and dedup.strip():
                trace_id = dedup
            # payload_for_store 直接使用原始 dict
            payload_for_store = dict(message)

        if trace_id:
            try:
                # event_store.topic = source（例如 scan_receive_path）
                # key = trace_id（便于查询）
                await writer.write_store(
                    session,
                    payload=payload_for_store,
                    key=trace_id,
                    trace_id=trace_id,
                )
            except Exception:
                # trace 写入失败不能影响主流程
                pass

        # 3) 尝试 commit：保持原有“能见度”语义
        try:
            await session.commit()
        except Exception:
            pass
        return int(ev.id)

    async def path(self, session: AsyncSession, mode: str, payload: Mapping[str, Any]) -> int:
        # payload 约定：包含 dedup=scan_ref
        return await self._write(session, f"scan_{mode}_path", "INFO", payload)

    async def probe(self, session: AsyncSession, mode: str, scan_ref: str) -> int:
        # message=scan_ref（保持原行为），用于 event_log；
        # _write 内部会自动识别 scan_ref 作为 trace_id，并写入 event_store。
        return await self._write(session, f"scan_{mode}_probe", "INFO", scan_ref)

    async def commit(self, session: AsyncSession, mode: str, payload: Mapping[str, Any]) -> int:
        # payload 约定：包含 dedup=scan_ref
        return await self._write(session, f"scan_{mode}_commit", "INFO", payload)

    async def other(self, session: AsyncSession, scan_ref: str) -> int:
        return await self._write(session, "scan_other_mode", "INFO", scan_ref)

    async def error(self, session: AsyncSession, mode: str, scan_ref: str, err: str) -> int:
        # 这里 payload 明确包含 dedup=scan_ref，便于 trace 识别
        return await self._write(
            session,
            f"scan_{mode}_error",
            "ERROR",
            {"dedup": scan_ref, "error": err},
        )
