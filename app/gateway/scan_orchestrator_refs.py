# app/gateway/scan_orchestrator_refs.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

UTC = timezone.utc


def scan_ref(raw: Dict[str, Any]) -> str:
    """
    生成 scan_ref：
    - device_id 优先从 raw["device_id"] / ctx["device_id"]；
    - 否则 fallback 到 "dev"。
    """
    ctx = raw.get("ctx") or {}
    if not isinstance(ctx, dict):
        ctx = {}

    dev = raw.get("device_id") or ctx.get("device_id") or "dev"
    dev = str(dev).strip()

    tokens = raw.get("tokens") or {}
    if not isinstance(tokens, dict):
        tokens = {}

    bc = str(raw.get("barcode") or tokens.get("barcode") or "").strip()
    ts = (raw.get("ts") or datetime.now(UTC).isoformat())[:16]
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
