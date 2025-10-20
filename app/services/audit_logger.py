# app/services/audit_logger.py
import logging
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

logger = logging.getLogger("audit")


def log_event(event_type: str, detail: str, *, extra: Optional[Mapping[str, Any]] = None) -> None:
    """
    统一审计日志：记录关键业务事件。
    - 使用 timezone-aware UTC 时间戳，避免 utcnow() 的弃用告警
    - 支持 extra 字段，便于结构化采集
    """
    ts = datetime.now(timezone.utc).isoformat()
    msg = f"[{ts}] {event_type}: {detail}"
    if extra:
        # 把 extra 作为结构化字段给 logging（许多采集器会认）
        logger.info(msg, extra={"audit": extra})
    else:
        logger.info(msg)
