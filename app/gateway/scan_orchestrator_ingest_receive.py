# app/gateway/scan_orchestrator_ingest_receive.py
from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditWriter
from app.core.tx import TxManager
from app.services.scan_handlers.receive_handler import handle_receive

from app.gateway.scan_orchestrator_dates import date_to_json


def _pick_raw_barcode(base_kwargs: Dict[str, Any]) -> str:
    """
    统一提取 raw_barcode（执行证据）
    - /scan 的上游可能用不同字段名塞进 base_kwargs（历史演进导致）
    - 这里做“尽力而为”的提取：raw_barcode > barcode > raw
    """
    raw = base_kwargs.get("raw_barcode")
    if raw is None or str(raw).strip() == "":
        raw = base_kwargs.get("barcode")
    if raw is None or str(raw).strip() == "":
        raw = base_kwargs.get("raw")
    return str(raw or "").strip()


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
    """
    /scan mode=receive 的两种语义（必须显性分离）：

    - probe=True：仅解析/试算/审计（不落账、不动库存）
    - probe=False：直接入库落账（不走旧执行层，仅用于明确的“直入库”场景）
    """
    kwargs = {
        **base_kwargs,
        "qty": qty,
        "trace_id": scan_ref_norm,
    }

    raw_barcode = _pick_raw_barcode(base_kwargs)
    parsed = base_kwargs.get("parsed")  # 若上游透传 parsed，这里就挂上；否则为 None

    audit_kwargs = {
        **kwargs,
        "production_date": date_to_json(kwargs.get("production_date")),
        "expiry_date": date_to_json(kwargs.get("expiry_date")),
    }
    if raw_barcode:
        audit_kwargs["raw_barcode"] = raw_barcode
    if isinstance(parsed, dict) and parsed:
        audit_kwargs["parsed"] = parsed

    _ = await audit.path(session, "receive", {"dedup": scan_ref_norm, "kw": audit_kwargs})
    evidence.append({"source": "scan_receive_path", "db": True})

    # ✅ 关键收紧：probe 模式不允许触发 handle_receive（不动账）
    if probe:
        ev = await audit.probe(session, "receive", scan_ref_norm)
        out: Dict[str, Any] = {
            "ok": True,
            "committed": False,
            "scan_ref": scan_ref_norm,
            "event_id": ev,
            "source": "scan_receive_probe",
            "evidence": evidence + [{"source": "scan_receive_probe", "db": True}],
            "errors": [],
            "item_id": item_id,
        }
        if raw_barcode:
            out["raw_barcode"] = raw_barcode
        if isinstance(parsed, dict) and parsed:
            out["parsed"] = parsed
        return out

    # probe=False：显式直入库（才允许落账）
    await TxManager.run(session, probe=False, fn=handle_receive, **kwargs)

    ev = await audit.commit(session, "receive", {"dedup": scan_ref_norm})
    out2: Dict[str, Any] = {
        "ok": True,
        "committed": True,
        "scan_ref": scan_ref_norm,
        "event_id": ev,
        "source": "scan_receive_commit",
        "evidence": evidence + [{"source": "scan_receive_commit", "db": True}],
        "errors": [],
        "item_id": item_id,
    }
    if raw_barcode:
        out2["raw_barcode"] = raw_barcode
    if isinstance(parsed, dict) and parsed:
        out2["parsed"] = parsed
    return out2
