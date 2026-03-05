# app/gateway/scan_orchestrator_refs.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

UTC = timezone.utc


def scan_ref(raw: Dict[str, Any]) -> str:
    """
    生成 scan_ref（用于 scan 流程的幂等、审计、trace 聚合）：

    - 以 "scan:" 开头（AuditWriter 会把它识别为 trace_id）；
    - device_id 优先从 raw["device_id"] / ctx["device_id"]；
    - mode 优先从 raw["mode"]；
    - barcode 优先从 raw["barcode"] / tokens["barcode"]；
    - ts 精度截断到分钟（[:16]），避免秒级抖动导致无法幂等；
    - ✅ 关键：若存在 mode，则把 mode 编进 ref，避免 receive/count 在同一分钟同批次撞 ref。

    兼容策略：
    - mode 缺失时保持旧格式：scan:{dev}:{ts}:{bc}
    - mode 存在时使用新格式：scan:{mode}:{dev}:{ts}:{bc}
    """
    ctx = raw.get("ctx") or {}
    if not isinstance(ctx, dict):
        ctx = {}

    dev = raw.get("device_id") or ctx.get("device_id") or "dev"
    dev = str(dev).strip()

    mode = raw.get("mode")
    mode_s = str(mode).strip().lower() if mode is not None else ""

    tokens = raw.get("tokens") or {}
    if not isinstance(tokens, dict):
        tokens = {}

    bc = str(raw.get("barcode") or tokens.get("barcode") or "").strip()
    ts = (raw.get("ts") or datetime.now(UTC).isoformat())[:16]

    if mode_s:
        return f"scan:{mode_s}:{dev}:{ts}:{bc}"
    return f"scan:{dev}:{ts}:{bc}"


async def normalize_ref(
    session: AsyncSession,
    ref: str,
    *,
    table: str = "stock_ledger",
    column: str = "ref",
) -> str:
    """将 ref 截断到数据库列允许的最大长度"""
    try:
        q = SA(
            """
            SELECT character_maximum_length
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = :t
               AND column_name = :c
            """
        )
        row = await session.execute(q, {"t": table, "c": column})
        maxlen = row.scalar()
        if isinstance(maxlen, int) and maxlen > 0 and len(ref) > maxlen:
            return ref[:maxlen]
    except Exception:
        pass
    return ref
