# app/gateway/scan_orchestrator_ingest_receive.py
from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditWriter
from app.core.tx import TxManager
from app.services.scan_handlers.receive_handler import handle_receive

from app.gateway.scan_orchestrator_dates import date_to_json


async def run_receive_flow(
    *,
    session: AsyncSession,
    audit: AuditWriter,
    scan_ref_norm: str,
    probe: bool,
    base_kwargs: Dict[str, Any],
    qty: int,
    item_id: int,
    evidence: List[Dict[str, Any]],
) -> Dict[str, Any]:
    kwargs = {
        **base_kwargs,
        "qty": qty,
        "trace_id": scan_ref_norm,
    }
    audit_kwargs = {
        **kwargs,
        "production_date": date_to_json(kwargs.get("production_date")),
        "expiry_date": date_to_json(kwargs.get("expiry_date")),
    }

    _ = await audit.path(session, "receive", {"dedup": scan_ref_norm, "kw": audit_kwargs})
    evidence.append({"source": "scan_receive_path", "db": True})

    await TxManager.run(session, probe=probe, fn=handle_receive, **kwargs)

    if probe:
        ev = await audit.probe(session, "receive", scan_ref_norm)
        return {
            "ok": True,
            "committed": False,
            "scan_ref": scan_ref_norm,
            "event_id": ev,
            "source": "scan_receive_probe",
            "evidence": evidence + [{"source": "scan_receive_probe", "db": True}],
            "errors": [],
            "item_id": item_id,
        }

    ev = await audit.commit(session, "receive", {"dedup": scan_ref_norm})
    return {
        "ok": True,
        "committed": True,
        "scan_ref": scan_ref_norm,
        "event_id": ev,
        "source": "scan_receive_commit",
        "evidence": evidence + [{"source": "scan_receive_commit", "db": True}],
        "errors": [],
        "item_id": item_id,
    }
