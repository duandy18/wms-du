from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import ProgrammingError

from app.api.deps import get_session
from app.services.scan_tokens import extract_scan_context

router = APIRouter(tags=["scan"])

_LOC_RE = re.compile(r"\bLOC:(\d+)\b", re.IGNORECASE)


def _fallback_loc_id_from_barcode(payload: Dict[str, Any]) -> Optional[int]:
    try:
        b = (payload.get("tokens") or {}).get("barcode") or ""
        m = _LOC_RE.search(str(b))
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return None


def _format_ref(occurred_at: datetime, device_id: Optional[str], loc_id: Optional[int]) -> str:
    iso = occurred_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    dev = device_id or "UNK"
    loc_part = f":LOC:{loc_id}" if loc_id is not None else ""
    return f"scan:{dev}:{iso}{loc_part}"


async def _insert_event_raw(
    session: AsyncSession, source: str, scan_ref: str, meta: Dict[str, Any], occurred_at: datetime
) -> None:
    insert_sql = text(
        """
        INSERT INTO event_log (source, message, meta, occurred_at)
        VALUES (:src, :msg, CAST(:meta AS jsonb), :ts)
        """
    )
    params = {"src": source, "msg": scan_ref, "meta": json.dumps(meta, ensure_ascii=False), "ts": occurred_at}
    try:
        await session.execute(insert_sql, params)
    except ProgrammingError as e:
        if 'relation "event_log"' in str(e):
            raise HTTPException(status_code=500, detail="event_log missing (run alembic migrations)") from e
        raise


async def _commit_and_get_event_id(session: AsyncSession, scan_ref: str, source: str) -> int:
    await session.commit()
    row = (
        await session.execute(
            text(
                """
                SELECT id
                  FROM event_log
                 WHERE message = :ref AND source = :src
                 ORDER BY id DESC
                 LIMIT 1
                """
            ),
            {"ref": scan_ref, "src": source},
        )
    ).first()
    if not row:
        raise HTTPException(status_code=500, detail=f"event not visible after commit: {source} {scan_ref}")
    return int(row[0])


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
        },
        "ref": scan_ref,
    }

    # pick probe
    if sc.mode == "pick" and probe:
        source = "scan_pick_probe"
        await _insert_event_raw(session, source, scan_ref, meta_base, occurred_at)
        ev_id = await _commit_and_get_event_id(session, scan_ref, source)
        return {
            "scan_ref": scan_ref,
            "ref": scan_ref,
            "source": source,
            "occurred_at": occurred_at.isoformat(),
            "committed": False,
            "event_id": ev_id,
            "result": {"hint": "pick probe"},
        }

    # === receive/putaway/count：probe 或 commit ===
    if sc.mode in {"receive", "putaway", "count"}:
        if probe:
            source = f"scan_{sc.mode}_probe"
            await _insert_event_raw(session, source, scan_ref, meta_base, occurred_at)
            ev_id = await _commit_and_get_event_id(session, scan_ref, source)
            return {
                "scan_ref": scan_ref,
                "ref": scan_ref,
                "source": source,
                "occurred_at": occurred_at.isoformat(),
                "committed": False,
                "event_id": ev_id,
                "result": {"hint": f"{sc.mode} probe"},
            }

        # -------- commit 真动作 --------
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
            result = await svc.transfer(
                session=session,
                item_id=sc.item_id,
                from_location_id=int(from_loc),
                to_location_id=loc_id,
                qty=int(sc.qty),
                reason="PUTAWAY",
                ref=scan_ref,
            )
            source = "scan_putaway_commit"

        else:  # sc.mode == "count"
            if sc.item_id is None or loc_id is None or sc.qty is None:
                raise HTTPException(status_code=400, detail="count requires ITEM, LOC, QTY(actual)")
            # ★ 修正：按 StockService.reconcile_inventory 的签名传参
            result = await svc.reconcile_inventory(
                session=session,
                item_id=sc.item_id,
                location_id=loc_id,
                counted_qty=int(sc.qty),
                apply=True,
                ref=scan_ref,
            )
            source = "scan_count_commit"

        # 落事件（commit）
        meta_commit = dict(meta_base)
        meta_commit["result"] = result
        await _insert_event_raw(session, source, scan_ref, meta_commit, occurred_at)
        ev_id = await _commit_and_get_event_id(session, scan_ref, source)
        return {
            "scan_ref": scan_ref,
            "ref": scan_ref,
            "source": source,
            "occurred_at": occurred_at.isoformat(),
            "committed": True,
            "event_id": ev_id,
            "result": result,
        }

    # pick commit
    if sc.mode == "pick":
        if sc.task_id is None or sc.item_id is None or sc.qty is None:
            raise HTTPException(status_code=400, detail="pick requires TASK, ITEM, QTY")
        try:
            from app.services.pick_service import PickService  # type: ignore
        except Exception as e:
            raise HTTPException(status_code=501, detail=f"pick commit not available: {e}")

        svc = PickService()
        result: Dict[str, Any]
        task_line_id = payload.get("task_line_id")

        if task_line_id:
            result = await svc.record_pick(
                session=session,
                task_line_id=int(task_line_id),
                from_location_id=loc_id or 0,
                item_id=sc.item_id,
                qty=sc.qty,
                scan_ref=scan_ref,
                operator=sc.operator,
            )
        else:
            used_by_context = False
            if hasattr(svc, "record_pick_by_context"):
                try:
                    result = await svc.record_pick_by_context(  # type: ignore[attr-defined]
                        session=session,
                        task_id=sc.task_id,
                        item_id=sc.item_id,
                        qty=sc.qty,
                        scan_ref=scan_ref,
                        location_id=loc_id,
                        device_id=sc.device_id,
                        operator=sc.operator,
                    )
                    used_by_context = True
                except TypeError:
                    result = await svc.record_pick_by_context(  # type: ignore[call-arg]
                        session=session,
                        task_id=sc.task_id,
                        item_id=sc.item_id,
                        qty=sc.qty,
                        scan_ref=scan_ref,
                        location_id=loc_id,
                    )
                    used_by_context = True

            if not used_by_context:
                row = (
                    await session.execute(
                        text(
                            """
                            SELECT ptl.id
                              FROM pick_task_lines ptl
                             WHERE ptl.task_id = :tid
                               AND ptl.item_id = :itm
                               AND ptl.status IN ('OPEN','PARTIAL')
                             ORDER BY ptl.id
                             LIMIT 1
                            """
                        ),
                        {"tid": sc.task_id, "itm": sc.item_id},
                    )
                ).first()
                if not row:
                    raise HTTPException(status_code=404, detail="no OPEN/PARTIAL line for task & item")
                tlid = int(row[0])
                result = await svc.record_pick(
                    session=session,
                    task_line_id=tlid,
                    from_location_id=loc_id or 0,
                    item_id=sc.item_id,
                    qty=sc.qty,
                    scan_ref=scan_ref,
                    operator=sc.operator,
                )

        source = "scan_pick_commit"
        meta_commit = dict(meta_base)
        meta_commit["result"] = result
        await _insert_event_raw(session, source, scan_ref, meta_commit, occurred_at)
        ev_id = await _commit_and_get_event_id(session, scan_ref, source)
        return {
            "scan_ref": scan_ref,
            "ref": scan_ref,
            "source": source,
            "occurred_at": occurred_at.isoformat(),
            "committed": True,
            "event_id": ev_id,
            "result": result,
        }

    raise HTTPException(status_code=400, detail="unsupported scan mode/flow")


@router.get("/scan/trace/{scan_ref}")
async def scan_trace(scan_ref: str, session: AsyncSession = Depends(get_session)) -> list[dict]:
    """
    返回指定 scan_ref 的事件腿 + 台账腿（即使没有行也返回 200 / []，避免 404）
    """
    sql = text(
        """
        SELECT scan_ref, event_id, occurred_at, source, device_id, operator, mode, barcode,
               input_json, output_json,
               ledger_id, ref_line, reason, delta, after_qty,
               item_id, warehouse_id, location_id, batch_id, batch_code, ledger_occurred_at
          FROM v_scan_trace
         WHERE scan_ref = :r
         ORDER BY occurred_at ASC, ref_line NULLS FIRST
        """
    )
    rows = (await session.execute(sql, {"r": scan_ref})).mappings().all()
    return [dict(r) for r in rows]
