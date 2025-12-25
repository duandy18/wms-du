# app/gateway/scan_orchestrator_ingest_count.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditWriter
from app.core.tx import TxManager
from app.services.scan_handlers.count_handler import handle_count

from app.gateway.scan_orchestrator_dates import date_to_json


async def run_count_flow(
    *,
    session: AsyncSession,
    audit: AuditWriter,
    scan_ref_norm: str,
    probe: bool,
    base_kwargs: Dict[str, Any],
    qty: int,
    item_id: int,
    wh_id: int,
    batch_code: Optional[str],
    production_date: Any,
    expiry_date: Any,
    evidence: List[Dict[str, Any]],
) -> Dict[str, Any]:
    kwargs = {
        **base_kwargs,
        "actual": qty,
        "trace_id": scan_ref_norm,
    }
    audit_kwargs = {
        **kwargs,
        "production_date": date_to_json(kwargs.get("production_date")),
        "expiry_date": date_to_json(kwargs.get("expiry_date")),
    }

    _ = await audit.path(session, "count", {"dedup": scan_ref_norm, "kw": audit_kwargs})
    evidence.append({"source": "scan_count_path", "db": True})

    count_payload: Dict[str, Any] | None = None
    try:
        result_obj = await TxManager.run(session, probe=probe, fn=handle_count, **kwargs)
        if isinstance(result_obj, dict):
            count_payload = result_obj
    except Exception as ex:
        ev = await audit.error(session, "count", scan_ref_norm, str(ex))
        return {
            "ok": False,
            "committed": False,
            "scan_ref": scan_ref_norm,
            "event_id": ev,
            "source": "scan_count_error",
            "evidence": evidence,
            "errors": [{"stage": "count", "error": str(ex)}],
            "item_id": item_id,
        }

    def enrich_with_count(payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(count_payload, dict):
            return payload

        actual_raw = count_payload.get("actual")
        delta_raw = count_payload.get("delta")

        try:
            actual = int(actual_raw)
            delta = int(delta_raw)
        except Exception:
            if "actual" in count_payload:
                payload["actual"] = actual_raw
            if "delta" in count_payload:
                payload["delta"] = delta_raw
            return payload

        before = count_payload.get("before")
        after = count_payload.get("after")

        if before is None:
            before = actual - delta
        if after is None:
            after = actual

        wh_val = count_payload.get("warehouse_id", wh_id)

        payload["warehouse_id"] = wh_val
        payload["actual"] = actual
        payload["delta"] = delta
        payload["before"] = before
        payload["before_qty"] = before
        payload["after"] = after
        payload["after_qty"] = after

        payload["batch_code"] = count_payload.get("batch_code") or batch_code

        prod = count_payload.get("production_date") or production_date
        exp = count_payload.get("expiry_date") or expiry_date
        if prod is not None:
            payload["production_date"] = prod
        if exp is not None:
            payload["expiry_date"] = exp

        if count_payload.get("item_id"):
            payload["item_id"] = count_payload["item_id"]

        return payload

    if probe:
        ev = await audit.probe(session, "count", scan_ref_norm)
        base = {
            "ok": True,
            "committed": False,
            "scan_ref": scan_ref_norm,
            "event_id": ev,
            "source": "scan_count_probe",
            "evidence": evidence,
            "errors": [],
            "item_id": item_id,
        }
        return enrich_with_count(base)

    ev = await audit.commit(session, "count", {"dedup": scan_ref_norm})
    base = {
        "ok": True,
        "committed": True,
        "scan_ref": scan_ref_norm,
        "event_id": ev,
        "source": "scan_count_commit",
        "evidence": evidence,
        "errors": [],
        "item_id": item_id,
    }
    return enrich_with_count(base)
