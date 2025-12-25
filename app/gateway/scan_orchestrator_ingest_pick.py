# app/gateway/scan_orchestrator_ingest_pick.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditWriter
from app.core.tx import TxManager
from app.services.scan_handlers.pick_handler import handle_pick

from app.gateway.scan_orchestrator_dates import date_to_json


async def run_pick_flow(
    *,
    session: AsyncSession,
    audit: AuditWriter,
    scan_ref_norm: str,
    probe: bool,
    parsed: Dict[str, Any],
    base_kwargs: Dict[str, Any],
    qty: int,
    item_id: int,
    wh_id: int,
    batch_code: Optional[str],
    production_date: Any,
    expiry_date: Any,
    evidence: List[Dict[str, Any]],
) -> Dict[str, Any]:
    # pick + probe：只做解析，不调用 handle_pick（不动账）
    if probe:
        parse_kwargs = {
            "item_id": item_id,
            "warehouse_id": wh_id,
            "batch_code": batch_code,
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

    # pick + commit：真正写入拣货任务（不扣库存）
    kwargs = {
        "item_id": item_id,
        "warehouse_id": wh_id,
        "batch_code": batch_code,
        "ref": scan_ref_norm,
        "qty": qty,
        "task_line_id": parsed.get("task_line_id"),
        "trace_id": scan_ref_norm,
    }
    audit_kwargs = {
        **kwargs,
        "production_date": date_to_json(production_date),
        "expiry_date": date_to_json(expiry_date),
    }

    _ = await audit.path(session, "pick", {"dedup": scan_ref_norm, "kw": audit_kwargs})
    evidence.append({"source": "scan_pick_path", "db": True})

    await TxManager.run(session, probe=probe, fn=handle_pick, **kwargs)

    # 这里的 probe 理论上不会发生（上面 probe 分支已 return），但保持原逻辑结构
    if probe:
        ev = await audit.probe(session, "pick", scan_ref_norm)
        return {
            "ok": True,
            "committed": False,
            "scan_ref": scan_ref_norm,
            "event_id": ev,
            "source": "scan_pick_probe",
            "evidence": evidence + [{"source": "scan_pick_probe", "db": True}],
            "errors": [],
            "item_id": item_id,
        }

    ev = await audit.commit(session, "pick", {"dedup": scan_ref_norm})
    return {
        "ok": True,
        "committed": True,
        "scan_ref": scan_ref_norm,
        "event_id": ev,
        "source": "scan_pick_commit",
        "evidence": evidence + [{"source": "scan_pick_commit", "db": True}],
        "errors": [],
        "item_id": item_id,
    }
