# app/services/platform_events.py
from __future__ import annotations

from app.services.platform_events_adapters import _ADAPTERS as _ADAPTERS
from app.services.platform_events_adapters import get_adapter as _get_adapter
from app.services.platform_events_classify import classify as _classify
from app.services.platform_events_classify import merge_lines as _merge_lines
from app.services.platform_events_error_log import log_error_isolated as _log_error_isolated
from app.services.platform_events_extractors import extract_ref as _extract_ref
from app.services.platform_events_extractors import extract_shop_id as _extract_shop_id
from app.services.platform_events_extractors import extract_state as _extract_state
from app.services.platform_events_handler import handle_event_batch

__all__ = [
    "handle_event_batch",
    "_ADAPTERS",
    "_get_adapter",
    "_extract_ref",
    "_extract_state",
    "_extract_shop_id",
    "_classify",
    "_merge_lines",
    "_log_error_isolated",
]
