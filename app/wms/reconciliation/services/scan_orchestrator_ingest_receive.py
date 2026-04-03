# app/wms/reconciliation/services/scan_orchestrator_ingest_receive.py
from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditWriter
from app.core.tx import TxManager
from app.wms.reconciliation.services.scan_orchestrator_dates import date_to_json
from app.wms.reconciliation.services.receive_handler import handle_receive


def _pick_raw_barcode(base_kwargs: Dict[str, Any]) -> str:
    raw = base_kwargs.get("raw_barcode")
    if raw is None or str(raw).strip() == "":
        raw = base_kwargs.get("barcode")
    if raw is None or str(raw).strip() == "":
        raw = base_kwargs.get("raw")
    return str(raw or "").strip()


async def _load_stocks_lot_qty(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    lot_id: int,
) -> int:
    row = (
        await session.execute(
            text(
                """
                SELECT qty
                  FROM stocks_lot
                 WHERE warehouse_id = :w
                   AND item_id      = :i
                   AND lot_id       = :l
                 LIMIT 1
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "l": int(lot_id)},
        )
    ).first()
    return int(row[0] or 0) if row else 0


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
    /scan mode=receive 的两种语义：

    - probe=True：仅解析/试算/审计（不落账、不动库存）
    - probe=False：直入库落账
    """
    kwargs = {
        **base_kwargs,
        "qty": qty,
        # scan 链路内 trace：以 scan_ref 作为 dedup/trace 锚
        "trace_id": scan_ref_norm,
    }

    raw_barcode = _pick_raw_barcode(base_kwargs)
    parsed = base_kwargs.get("parsed")

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

    if probe:
        ev = await audit.probe(session, "receive", scan_ref_norm)
        out_probe: Dict[str, Any] = {
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
            out_probe["raw_barcode"] = raw_barcode
        if isinstance(parsed, dict) and parsed:
            out_probe["parsed"] = parsed
        return out_probe

    # 直入库
    res = await TxManager.run(session, probe=False, fn=handle_receive, **kwargs)

    applied = True
    lot_id: int | None = None
    if isinstance(res, dict):
        applied = bool(res.get("applied", True))
        if res.get("lot_id") is not None:
            try:
                lot_id = int(res.get("lot_id"))
            except Exception:
                lot_id = None

    # 幂等命中：不写 scan_receive_commit，只写 scan_receive_idempotent
    if not applied:
        ev = await audit.idempotent(session, "receive", {"dedup": scan_ref_norm})
        out_hit: Dict[str, Any] = {
            "ok": True,
            "committed": False,
            "scan_ref": scan_ref_norm,
            "event_id": ev,
            "source": "scan_receive_idempotent",
            "evidence": evidence
            + [
                {"source": "scan_receive_idempotent", "db": True},
                {"source": "idempotency_hit", "db": True},
            ],
            "errors": [],
            "item_id": item_id,
        }
        if raw_barcode:
            out_hit["raw_barcode"] = raw_barcode
        if isinstance(parsed, dict) and parsed:
            out_hit["parsed"] = parsed
        return out_hit

    # 正常 commit
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

    # 回填 before/after/delta（ScanResponse 有 before/after/before_qty/after_qty/delta）
    wh_id = int(base_kwargs.get("warehouse_id") or 0)
    if lot_id is not None and wh_id > 0:
        after_qty = await _load_stocks_lot_qty(session, warehouse_id=wh_id, item_id=int(item_id), lot_id=int(lot_id))
        delta = int(qty)
        before_qty = int(after_qty) - int(delta)

        out2["delta"] = int(delta)
        out2["after_qty"] = int(after_qty)
        out2["before_qty"] = int(before_qty)
        out2["before"] = int(before_qty)
        out2["after"] = int(after_qty)

    return out2
