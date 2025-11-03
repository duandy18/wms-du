# app/api/routers/scan.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import json
import re

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session

router = APIRouter()

# ---------- helpers ----------

def _format_ref(ts: datetime, device_id: Optional[str], location_id: Optional[int]) -> str:
    did = (device_id or "unknown").lower()
    loc = f"{location_id}" if location_id is not None else "unknown"
    return f"scan:{did}:{ts.isoformat()}:loc:{loc}".lower()


async def _insert_event_raw(
    session: AsyncSession,
    source: str,
    message: str | Dict[str, Any],
    occurred_at: datetime,
) -> int:
    msg_text = message if isinstance(message, str) else json.dumps(message, ensure_ascii=False)
    row = await session.execute(
        sa.text(
            """
            INSERT INTO event_log(source, message, occurred_at)
            VALUES (:source, :message, :occurred_at)
            RETURNING id
            """
        ),
        {"source": source, "message": msg_text, "occurred_at": occurred_at},
    )
    return int(row.scalar_one())


async def _commit_and_get_event_id(
    session: AsyncSession, source: str, message: str | Dict[str, Any], occurred_at: datetime
) -> int:
    ev_id = await _insert_event_raw(session, source, message, occurred_at)
    await session.commit()
    return ev_id


class ScanCtx(Dict[str, Any]):
    __slots__ = ()

    @property
    def mode(self) -> str:  # type: ignore[override]
        return (self.get("mode") or "").lower()

    @property
    def device_id(self) -> Optional[str]:
        ctx = self.get("ctx") or {}
        return ctx.get("device_id")

    @property
    def operator(self) -> Optional[str]:
        ctx = self.get("ctx") or {}
        return ctx.get("operator")

    @property
    def task_id(self) -> Optional[int]:
        return self.get("task_id")

    @property
    def item_id(self) -> Optional[int]:
        return self.get("item_id")

    @property
    def qty(self) -> Optional[int]:
        return self.get("qty")

    @property
    def location_id(self) -> Optional[int]:
        return self.get("location_id")


_BARCODE_INT = re.compile(r"\b(\w+):([-\w\.]+)\b", re.I)

def extract_scan_context(payload: Dict[str, Any]) -> ScanCtx:
    out: Dict[str, Any] = {
        "mode": (payload.get("mode") or "").lower(),
        "ctx": payload.get("ctx") or {},
    }
    tokens = payload.get("tokens") or {}
    barcode = tokens.get("barcode") or ""
    if isinstance(barcode, str) and barcode:
        kv = {m.group(1).upper(): m.group(2) for m in _BARCODE_INT.finditer(barcode)}
        if "TASK" in kv:
            try: out["task_id"] = int(kv["TASK"])
            except ValueError: pass
        if "LOC" in kv:
            try: out["location_id"] = int(kv["LOC"])
            except ValueError: pass
        if "ITEM" in kv:
            try: out["item_id"] = int(kv["ITEM"])
            except ValueError: pass
        if "QTY" in kv:
            try: out["qty"] = int(kv["QTY"])
            except ValueError: pass
    for k in ("task_id", "location_id", "item_id", "qty"):
        if k in payload and payload[k] is not None:
            out[k] = payload[k]
    return ScanCtx(out)


def _fallback_loc_id_from_barcode(payload: Dict[str, Any]) -> Optional[int]:
    tokens = payload.get("tokens") or {}
    barcode = tokens.get("barcode") or ""
    if isinstance(barcode, str):
        m = re.search(r"\bloc:(\d+)\b", barcode, re.I)
        if m:
            return int(m.group(1))
    return None

# ---------- endpoint ----------

@router.post("/scan")
async def scan_gateway(
    payload: Dict[str, Any], session: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    sc = extract_scan_context(payload)
    if sc.mode not in {"pick", "receive", "putaway", "count"}:
        raise HTTPException(status_code=400, detail="unsupported mode")

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
        },
        "ref": scan_ref,
    }

    # ---------- pick ----------
    if sc.mode == "pick":
        if probe:
            source = "scan_pick_probe"
            ev_id = await _commit_and_get_event_id(session, source, scan_ref, occurred_at)
            return {
                "scan_ref": scan_ref,
                "ref": scan_ref,
                "source": source,
                "occurred_at": occurred_at.isoformat(),
                "committed": False,
                "event_id": ev_id,
                "result": {"hint": "pick probe"},
            }
        else:
            try:
                from app.services.pick_service import PickService  # type: ignore
            except Exception as e:  # pragma: no cover
                raise HTTPException(status_code=500, detail=f"pick service missing: {e}")

            svc = PickService()
            task_line_id = payload.get("task_line_id")
            if sc.item_id is None or loc_id is None or sc.qty is None:
                raise HTTPException(status_code=400, detail="pick requires TASK/ITEM/LOC/QTY")

            result = await svc.record_pick(
                session=session,
                task_line_id=int(task_line_id) if task_line_id is not None else (sc.task_id or 0),
                from_location_id=loc_id,
                item_id=sc.item_id,
                qty=int(sc.qty),
                scan_ref=scan_ref,
                operator=sc.operator,
            )
            source = "scan_pick_commit"
            ev_id = await _commit_and_get_event_id(session, source, scan_ref, occurred_at)
            return {
                "scan_ref": scan_ref,
                "ref": scan_ref,
                "source": source,
                "occurred_at": occurred_at.isoformat(),
                "committed": True,
                "event_id": ev_id,
                "result": result,
            }

    # ---------- receive / putaway / count ----------
    if probe:
        source = f"scan_{sc.mode}_probe"
        ev_id = await _commit_and_get_event_id(session, source, scan_ref, occurred_at)
        return {
            "scan_ref": scan_ref,
            "ref": scan_ref,
            "source": source,
            "occurred_at": occurred_at.isoformat(),
            "committed": False,
            "event_id": ev_id,
            "result": {"hint": f"{sc.mode} probe"},
        }

    # 真动作
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
        msg: str | Dict[str, Any] = {**meta_base["input"], "ref": scan_ref}

    elif sc.mode == "putaway":
        from_loc = payload.get("from_location_id")
        if from_loc is None:
            raise HTTPException(status_code=400, detail="putaway requires from_location_id")
        if sc.item_id is None or loc_id is None or sc.qty is None:
            raise HTTPException(status_code=400, detail="putaway requires ITEM, LOC, QTY")

        qty = int(sc.qty)

        # 两次 adjust 写双腿账页（负出源位，正入目标位）
        await svc.adjust(
            session=session,
            item_id=sc.item_id,
            location_id=int(from_loc),
            delta=-qty,
            reason="PUTAWAY",
            ref=scan_ref,
        )
        await svc.adjust(
            session=session,
            item_id=sc.item_id,
            location_id=loc_id,
            delta=+qty,
            reason="PUTAWAY",
            ref=scan_ref,
        )

        # 兜底：若 adjust 内部对 reason 做了标准化或忽略，这里强制把本次 ref 对应账页的 reason 统一修正为 PUTAWAY
        await session.execute(
            sa.text("UPDATE stock_ledger SET reason='PUTAWAY' WHERE ref=:ref"),
            {"ref": scan_ref},
        )
        await session.commit()

        source = "scan_putaway_commit"
        msg = {**meta_base["input"], "ref": scan_ref}
        result = {"moved": qty, "from_location_id": int(from_loc), "to_location_id": loc_id}

        ev_id = await _commit_and_get_event_id(session, source, msg, occurred_at)
        return {
            "scan_ref": scan_ref,
            "ref": scan_ref,
            "source": source,
            "occurred_at": occurred_at.isoformat(),
            "committed": True,
            "event_id": ev_id,
            "result": result,
        }

    else:  # sc.mode == "count"
        if sc.item_id is None or loc_id is None or sc.qty is None:
            raise HTTPException(status_code=400, detail="count requires ITEM, LOC, QTY(actual)")
        result = await svc.reconcile_inventory(
            session=session,
            item_id=sc.item_id,
            location_id=loc_id,
            counted_qty=int(sc.qty),
            apply=True,
            ref=scan_ref,
        )
        source = "scan_count_commit"
        msg = {**meta_base["input"], "ref": scan_ref}

    ev_id = await _commit_and_get_event_id(session, source, msg, occurred_at)
    return {
        "scan_ref": scan_ref,
        "ref": scan_ref,
        "source": source,
        "occurred_at": occurred_at.isoformat(),
        "committed": True,
        "event_id": ev_id,
        "result": result,
    }
