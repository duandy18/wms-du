# app/wms/scan/services/scan_orchestrator_ingest_pick.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditWriter

from app.wms.scan.services.scan_orchestrator_dates import date_to_json


async def run_pick_flow(
    *,
    session: AsyncSession,
    audit: AuditWriter,
    scan_ref_norm: str,
    parsed: Dict[str, Any],
    qty: int,
    item_id: int,
    wh_id: int,
    lot_code: Optional[str],
    production_date: Any,
    expiry_date: Any,
    evidence: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    /scan 已收口为 pick probe 工具层：

    - 只做条码 / 商品 / 包装识别；
    - 不扣库存；
    - 不写出库执行事实；
    - 真正执行入口是 /orders/{platform}/{shop_id}/{ext_order_no}/pick。
    """
    parse_kwargs = {
        "item_id": item_id,
        "warehouse_id": wh_id,
        "lot_code": lot_code,
        "ref": scan_ref_norm,
        "qty": qty,
        "task_line_id": parsed.get("task_line_id"),
        "trace_id": scan_ref_norm,
        "production_date": production_date,
        "expiry_date": expiry_date,
    }
    audit_kwargs = {
        **parse_kwargs,
        "production_date": date_to_json(parse_kwargs.get("production_date")),
        "expiry_date": date_to_json(parse_kwargs.get("expiry_date")),
    }

    _ = await audit.path(session, "pick", {"dedup": scan_ref_norm, "kw": audit_kwargs})
    evidence.append({"source": "scan_pick_path", "db": True})

    ev = await audit.probe(session, "pick", scan_ref_norm)
    return {
        "ok": True,
        "committed": False,
        "scan_ref": scan_ref_norm,
        "event_id": ev,
        "source": "scan_pick_probe_parse_only",
        "evidence": evidence + [{"source": "scan_pick_probe", "db": True}],
        "errors": [],
        "item_id": item_id,
    }
