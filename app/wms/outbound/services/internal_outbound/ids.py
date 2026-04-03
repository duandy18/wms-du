# app/wms/outbound/services/internal_outbound/ids.py
from __future__ import annotations

from datetime import datetime, timezone

UTC = timezone.utc


def gen_doc_no(warehouse_id: int) -> str:
    now = datetime.now(UTC)
    return f"INT-OUT:WH{warehouse_id}:{now.strftime('%Y%m%d%H%M%S')}"


def gen_trace_id(warehouse_id: int, doc_no: str) -> str:
    return f"INT-OUT:{warehouse_id}:{doc_no}"
