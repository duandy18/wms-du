# app/services/process_event.py
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.services._event_writer import EventWriter


async def process_platform_events(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Webhook 入口使用的服务函数（由 app/api/routers/webhooks.py 引用）。

    约束（工程护栏）：
    - active core code 禁止出现旧时代的“库位维度”语义；只能留在明确标注的 legacy/transition 区域
    - Scope 第一阶段期间，本模块仅做“审计落库 + 忽略返回”，不做任何库存/出库推进

    说明：
    - 生产事件推进由 Celery task `wms.process_event`（app/tasks.py）承担
    - Webhook 入口在此阶段不做业务推进，避免引入历史维度依赖
    """
    p = (platform or "").strip().lower()
    s = (shop_id or "").strip()

    writer = EventWriter(source="webhook-process-event")
    await writer.write_json(
        session,
        level="INFO",
        message={"ignored": True, "platform": p, "shop_id": s},
        meta={"payload": payload},
    )

    # 兜底提交：若上层已有事务则 no-op；若没有则确保审计落库
    try:
        await session.commit()
    except Exception:
        pass

    return {"ignored": True, "platform": p, "shop_id": s}
