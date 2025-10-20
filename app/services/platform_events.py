from typing import Any, Dict, List

from app.services.audit_logger import log_event
from app.services.platform_adapter import PDDAdapter


async def handle_event_batch(events: List[Dict[str, Any]]) -> None:
    """多平台事件批处理入口。"""
    for raw in events:
        platform = raw.get("platform")
        adapter = _get_adapter(platform)
        try:
            parsed = await adapter.parse_event(raw)
            outbound_task = await adapter.to_outbound_task(parsed)
            log_event("event_processed", f"{platform}:{parsed.get('order_id')}")
            # TODO: 调用 OutboundService.apply_event(outbound_task)
        except Exception as e:
            log_event("event_error", f"{platform}: {e}")


def _get_adapter(platform: str):
    if platform == "pdd":
        return PDDAdapter()
    # TODO: 扩展 TAOBAOAdapter, JDAdapter
    raise ValueError(f"Unsupported platform: {platform}")
