# app/api/routers/platform_shops_helpers.py
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# 允许的前端 redirect_uri 白名单（防钓鱼回调）
# 多个地址用逗号分隔，例如：
# WMS_OAUTH_REDIRECT_ALLOWLIST=http://127.0.0.1:5173,http://localhost:5173
_OAUTH_ALLOWLIST_ENV = os.getenv("WMS_OAUTH_REDIRECT_ALLOWLIST", "")
OAUTH_REDIRECT_ALLOWLIST = {u.strip() for u in _OAUTH_ALLOWLIST_ENV.split(",") if u.strip()}


async def audit(session: AsyncSession, ref: str, meta: Dict[str, Any]) -> None:
    """
    轻量级审计记录。

    - 如果存在 audit_event 表且结构兼容，就插进去；
    - 如果失败（表不存在 / 结构不兼容），就直接吞掉，不影响主流程。
    """
    payload = {
        "ref": ref,
        "meta": meta,
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": "platform_oauth",
    }
    try:
        await session.execute(
            text(
                """
                INSERT INTO audit_event (ref, source, payload, created_at)
                VALUES (:ref, :source, :payload, now())
                """
            ),
            {
                "ref": ref,
                "source": "platform_shops",
                "payload": json.dumps(payload, ensure_ascii=False),
            },
        )
        await session.commit()
    except Exception:
        await session.rollback()


def mask(token: str, keep: int = 4) -> str:
    """
    打印时对 token 做脱敏展示。
    """
    if not token:
        return ""
    if len(token) <= keep:
        return "*" * len(token)
    return token[:keep] + "..."
