# app/api/routers/scan.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session

router = APIRouter()


# ---------- 扫码上下文 ----------
class ScanContext:
    def __init__(
        self,
        *,
        mode: str,
        task_id: Optional[int],
        location_id: Optional[int],
        item_id: Optional[int],
        qty: Optional[int],
        device_id: str,
        operator: Optional[str],
    ):
        self.mode = mode
        self.task_id = task_id
        self.location_id = location_id
        self.item_id = item_id
        self.qty = qty
        self.device_id = device_id
        self.operator = operator


def extract_scan_context(payload: Dict[str, Any]) -> ScanContext:
    tokens = payload.get("tokens") or {}
    barcode = tokens.get("barcode") or ""
    kv: Dict[str, str] = {}
    for part in str(barcode).replace(",", " ").split():
        if ":" in part:
            k, v = part.split(":", 1)
            kv[k.strip().upper()] = v.strip()

    def _to_int(s: Optional[str]) -> Optional[int]:
        try:
            return int(str(s)) if s is not None else None
        except Exception:
            return None

    mode = str(payload.get("mode") or "").strip().lower()
    return ScanContext(
        mode=mode,
        task_id=_to_int(kv.get("TASK")),
        location_id=_to_int(kv.get("LOC")),
        item_id=_to_int(kv.get("ITEM")),
        qty=_to_int(kv.get("QTY")),
        device_id=str((payload.get("ctx") or {}).get("device_id") or "RF"),
        operator=(payload.get("ctx") or {}).get("operator"),
    )


# ---------- 事件写入（无 ref 列版） ----------
async def _insert_event_raw(
    session: AsyncSession,
    source: str,
    meta_input: Dict[str, Any],
    occurred_at: datetime,
) -> int:
    """
    直接向 event_log(source, message, occurred_at) 插入，并返回事件ID。
    注意：不要在 SQL 中写 :msg::text，否则会与 asyncpg 的占位符混用报错。
    """
    msg = json.dumps(meta_input or {}, ensure_ascii=False)
    row = await session.execute(
        text(
            """
            INSERT INTO event_log(source, message, occurred_at)
            VALUES (:src, :msg, :ts)
            RETURNING id
            """
        ),
        {"src": source, "msg": msg, "ts": occurred_at},
    )
    event_id = int(row.scalar_one())
    await session.commit()
    return event_id


def _format_ref(ts: datetime, device_id: str, loc_id: Optional[int]) -> str:
    loc = loc_id if loc_id is not None else 0
    return f"SCAN:scan:{device_id}:{ts.isoformat()}:LOC:{loc}"


def _fallback_loc_id_from_barcode(payload: Dict[str, Any]) -> Optional[int]:
    tokens = payload.get("tokens") or {}
    barcode = tokens.get("barcode") or ""
    for part in str(barcode).replace(",", " ").split():
        if part.upper().startswith("LOC:"):
            try:
                return int(part.split(":", 1)[1])
            except Exception:
                return None
    return None


@router.post("/scan")
async def scan_gateway(
    payload: Dict[str, Any], session: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    sc = extract_scan_context(payload)
    if sc.mode not in {"pick", "receive", "putaway", "count"}:
        raise HTTPException(status_code=400, detail="invalid mode")

    occurred_at = datetime.now(timezone.utc)
    probe = bool(payload.get("probe", False))
    loc_id = sc.location_id if sc.location_id is not None else _fallback_loc_id_from_barcode(payload)
    scan_ref = _format_ref(occurred_at, sc.device_id, loc_id)

    meta_base: Dict[str, Any] = {
        "occurred_at": occurred_at.isoformat(),
        "ctx": {"device_id": sc.device_id, "operator": sc.operator},
        "input": {
            "mode": sc.mode,
            "task_id": sc.task_id,
            "item_id": sc.item_id,
            "qty": sc.qty,
            "location_id": loc_id,
            "ref": scan_ref,
        },
    }

    # pick probe
    if sc.mode == "pick" and probe:
        source = "scan_pick_probe"
        ev_id = await _insert_event_raw(session, source, meta_base.get("input", {}), occurred_at)
        return {
            "scan_ref": scan_ref,
            "source": source,
            "occurred_at": occurred_at.isoformat(),
            "committed": False,
            "event_id": ev_id,
            "result": {"hint": "pick probe"},
        }

    # receive / putaway / count
    if sc.mode in {"receive", "putaway", "count"}:
        if probe:
            source = f"scan_{sc.mode}_probe"
            ev_id = await _insert_event_raw(session, source, meta_base.get("input", {}), occurred_at)
            return {
                "scan_ref": scan_ref,
                "source": source,
                "occurred_at": occurred_at.isoformat(),
                "committed": False,
                "event_id": ev_id,
                "result": {"hint": f"{sc.mode} probe"},
            }

        # commit 真动作
        from app.services.stock_service import StockService
        svc = StockService()

        if sc.mode == "receive":
            if sc.item_id is None or loc_id is None or sc.qty is None:
                raise HTTPException(status_code=400, detail="receive requires ITEM, LOC, QTY")
            result = await svc.adjust(
                session=session,
                item_id=sc.item_id,
                location_id=loc_id,
                delta=+int(sc.qty),
                reason="INBOUND",
                ref=scan_ref,
            )
            source = "scan_receive_commit"

        elif sc.mode == "putaway":
            from_loc = payload.get("from_location_id")
            if from_loc is None:
                raise HTTPException(status_code=400, detail="putaway requires from_location_id")
            if sc.item_id is None or loc_id is None or sc.qty is None:
                raise HTTPException(status_code=400, detail="putaway requires ITEM, LOC, QTY")
            # 注意：transfer 不接收 reason
            result = await svc.transfer(
                session=session,
                item_id=sc.item_id,
                from_location_id=int(from_loc),
                to_location_id=loc_id,
                qty=int(sc.qty),
                ref=scan_ref,
            )
            source = "scan_putaway_commit"

        else:  # count
            if sc.item_id is None or loc_id is None or sc.qty is None:
                raise HTTPException(status_code=400, detail="count requires ITEM, LOC, QTY(actual)")
            # 注意：reconcile_inventory 接收 counted_qty，而非 qty
            result = await svc.reconcile_inventory(
                session=session,
                item_id=sc.item_id,
                location_id=loc_id,
                counted_qty=int(sc.qty),
                apply=True,
                ref=scan_ref,
            )
            source = "scan_count_commit"

        ev_id = await _insert_event_raw(session, source, meta_base.get("input", {}), occurred_at)
        return {
            "scan_ref": scan_ref,
            "source": source,
            "occurred_at": occurred_at.isoformat(),
            "committed": True,
            "event_id": ev_id,
            "result": result,
        }

    raise HTTPException(status_code=400, detail="unsupported mode")
