# app/gateway/scan_orchestrator_ingest.py
from __future__ import annotations

from datetime import timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditWriter

from app.gateway.scan_orchestrator_parse import parse_scan
from app.gateway.scan_orchestrator_refs import normalize_ref, scan_ref
from app.gateway.scan_orchestrator_tokens import ALLOWED_SCAN_MODES

from app.gateway.scan_orchestrator_ingest_count import run_count_flow
from app.gateway.scan_orchestrator_ingest_receive import run_receive_flow
from app.gateway.scan_orchestrator_ingest_pick import run_pick_flow

UTC = timezone.utc
AUDIT = AuditWriter()


async def ingest(scan: Dict[str, Any], session: Optional[AsyncSession]) -> Dict[str, Any]:
    """
    v2 扫描编排器（receive / pick / count，putaway 禁用）：
      - 解析 ScanRequest / barcode / GS1 / item_barcodes / BarcodeResolver
      - probe 模式：
          * receive / count：跑 handler，但不提交 Tx
          * pick：只做解析，不调用 handle_pick，不动账（条码→item_id 解析服务）
      - commit 模式：TxManager + 对应 handler
      - 统一返回结构（ok/committed/scan_ref/event_id/evidence/errors）
    """
    if session is None:
        dummy = scan_ref(scan)
        return {
            "ok": False,
            "committed": False,
            "scan_ref": dummy,
            "event_id": None,
            "source": None,
            "evidence": [],
            "errors": [{"stage": "ingest", "error": "missing session"}],
            "item_id": None,
        }

    (
        parsed,
        mode,
        probe,
        qty,
        item_id,
        batch_code,
        wh_id,
        production_date,
        expiry_date,
    ) = await parse_scan(scan, session)

    # ✅ 关键：确保 scan_ref 一定含 mode（哪怕调用方没传、parse_scan 推导了）
    scan_with_mode: Dict[str, Any] = dict(scan or {})
    scan_with_mode["mode"] = mode

    scan_ref_norm = await normalize_ref(session, scan_ref(scan_with_mode))
    evidence: List[Dict[str, Any]] = []

    if mode not in ALLOWED_SCAN_MODES:
        ev = await AUDIT.other(session, scan_ref_norm)
        return {
            "ok": False,
            "committed": False,
            "scan_ref": scan_ref_norm,
            "event_id": ev,
            "source": "scan_feature_disabled",
            "evidence": [{"source": "scan_feature_disabled", "db": True}],
            "errors": [{"stage": "ingest", "error": "FEATURE_DISABLED: putaway"}],
            "item_id": item_id,
        }

    base_kwargs: Dict[str, Any] = {
        "item_id": item_id,
        "warehouse_id": wh_id,
        "batch_code": batch_code,
        "ref": scan_ref_norm,
        "production_date": production_date,
        "expiry_date": expiry_date,
    }

    try:
        if mode == "count":
            return await run_count_flow(
                session=session,
                audit=AUDIT,
                scan_ref_norm=scan_ref_norm,
                probe=probe,
                base_kwargs=base_kwargs,
                qty=qty,
                item_id=item_id,
                wh_id=wh_id,
                batch_code=batch_code,
                production_date=production_date,
                expiry_date=expiry_date,
                evidence=evidence,
            )

        if mode == "receive":
            return await run_receive_flow(
                session=session,
                audit=AUDIT,
                scan_ref_norm=scan_ref_norm,
                probe=probe,
                base_kwargs=base_kwargs,
                qty=qty,
                item_id=item_id,
                evidence=evidence,
            )

        # pick
        return await run_pick_flow(
            session=session,
            audit=AUDIT,
            scan_ref_norm=scan_ref_norm,
            probe=probe,
            parsed=parsed,
            base_kwargs=base_kwargs,
            qty=qty,
            item_id=item_id,
            wh_id=wh_id,
            batch_code=batch_code,
            production_date=production_date,
            expiry_date=expiry_date,
            evidence=evidence,
        )

    except Exception as e:
        ev = await AUDIT.error(session, mode, scan_ref_norm, str(e))
        return {
            "ok": False,
            "committed": False,
            "scan_ref": scan_ref_norm,
            "event_id": ev,
            "source": f"scan_{mode}_error",
            "evidence": evidence,
            "errors": [{"stage": mode, "error": str(e)}],
            "item_id": item_id,
        }
