# app/oms/services/platform_events_extractors.py
from __future__ import annotations

from typing import Any, Dict


def extract_ref(raw: Dict[str, Any]) -> str:
    return str(
        raw.get("order_sn")
        or raw.get("tid")
        or raw.get("orderId")
        or raw.get("order_id")
        or raw.get("id")
        or ""
    )


def extract_state(raw: Dict[str, Any]) -> str:
    return str(raw.get("status") or raw.get("trade_status") or raw.get("orderStatus") or "")


def extract_store_code(raw: Dict[str, Any]) -> str:
    return str(
        raw.get("store_code")
        or raw.get("store")
        or raw.get("store_id")
        or raw.get("seller_id")
        or raw.get("author_id")
        or raw.get("storeCode")
        or ""
    )
