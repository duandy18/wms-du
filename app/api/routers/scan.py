from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.services.scan_tokens import extract_scan_context
from app.api.deps import get_session  # 由 main.py 动态导出

router = APIRouter(tags=["scan"])


def _make_scan_ref(device_id: Optional[str], sc_tokens: Dict[str, Any]) -> str:
    iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    dev = device_id or "UNK"
    loc_part = f":LOC:{sc_tokens['location_id']}" if sc_tokens.get("location_id") else ""
    return f"scan:{dev}:{iso}{loc_part}"


async def _write_event(
    session: AsyncSession, source: str, scan_ref: str, meta: Dict[str, Any], occurred_at: datetime
) -> int:
    """
    事件落表：显式把 meta 序列化为 JSON，并强制转换为 jsonb。
    避免 asyncpg 在无类型 hint 时把 dict 当作 bytes 处理而报错。
    """
    sql = text(
        """
        INSERT INTO event_log (source, message, meta, occurred_at)
        VALUES (:src, :msg, CAST(:meta AS jsonb), :ts)
        RETURNING id
        """
    )
    meta_str = json.dumps(meta, ensure_ascii=False)
    r = await session.execute(sql, {"src": source, "msg": scan_ref, "meta": meta_str, "ts": occurred_at})
    return r.scalar_one()


@router.post("/scan")
async def scan_gateway(payload: Dict[str, Any], session: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
    """
    聚合网关：
    - 统一解析 TASK:/LOC:/ITEM:/QTY
    - 先实现 pick 的 probe/commit；其余三种模式（receive/putaway/count）先支持 probe
    - 事件全部写入 event_log（jsonb + occurred_at），v_scan_trace 可直接复盘
    """
    sc = extract_scan_context(payload)
    if sc.mode not in {"pick", "receive", "putaway", "count"}:
        raise HTTPException(status_code=400, detail="invalid mode")

    occurred_at = datetime.now(timezone.utc)
    probe = bool(payload.get("probe", False))
    scan_ref = _make_scan_ref(sc.device_id, {"location_id": sc.location_id})

    # 通用 meta
    meta_base: Dict[str, Any] = {
        "occurred_at": occurred_at.isoformat(),
        "ctx": {"device_id": sc.device_id, "operator": sc.operator},
        "input": {
            "mode": sc.mode,
            "task_id": sc.task_id,
            "item_id": sc.item_id,
            "qty": sc.qty,
            "location_id": sc.location_id,
        },
        "ref": scan_ref,
    }

    # ---- 其它三种模式：现阶段仅支持 probe ----
    if sc.mode in {"receive", "putaway", "count"}:
        if not probe:
            raise HTTPException(status_code=501, detail=f"mode '{sc.mode}' commit not implemented yet")
        ev_id = await _write_event(session, f"scan_{sc.mode}_probe", scan_ref, meta_base, occurred_at)
        await session.commit()
        return {"scan_ref": scan_ref, "committed": False, "event_id": ev_id, "result": {"hint": f"{sc.mode} probe"}}

    # --------------------- pick ---------------------
    # 基本必需项
    if sc.task_id is None or sc.item_id is None or sc.qty is None:
        raise HTTPException(status_code=400, detail="pick requires TASK, ITEM, QTY")

    if probe:
        ev_id = await _write_event(session, "scan_pick_probe", scan_ref, meta_base, occurred_at)
        await session.commit()
        return {"scan_ref": scan_ref, "committed": False, "event_id": ev_id, "result": {"hint": "pick probe"}}

    # 真动作：延迟导入，避免应用启动期的硬依赖
    try:
        from app.services.pick_service import PickService  # type: ignore
    except Exception as e:
        raise HTTPException(status_code=501, detail=f"pick commit not available: {e}")

    svc = PickService()  # 若需注入真实 StockService，可在此传入

    # 优先按上下文定位行（前端无需提供 task_line_id）；若 by_context 不可用，则在网关内兜底查询一条 OPEN/PARTIAL 行
    result: Dict[str, Any]
    task_line_id = payload.get("task_line_id")
    if task_line_id:
        # 兼容路径：显式行号
        result = await svc.record_pick(
            session=session,
            task_line_id=int(task_line_id),
            from_location_id=sc.location_id or 0,
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
                    location_id=sc.location_id,
                    device_id=sc.device_id,
                    operator=sc.operator,
                )
                used_by_context = True
            except TypeError:
                # 签名不匹配（无 device_id / operator 等），用精简参重试
                result = await svc.record_pick_by_context(  # type: ignore[call-arg]
                    session=session,
                    task_id=sc.task_id,
                    item_id=sc.item_id,
                    qty=sc.qty,
                    scan_ref=scan_ref,
                    location_id=sc.location_id,
                )
                used_by_context = True

        if not used_by_context:
            # 兜底：在网关内定位一条 OPEN/PARTIAL 行，再调用 record_pick()
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
                from_location_id=sc.location_id or 0,
                item_id=sc.item_id,
                qty=sc.qty,
                scan_ref=scan_ref,
                operator=sc.operator,
            )

    meta_commit = dict(meta_base)
    meta_commit["result"] = result
    ev_id = await _write_event(session, "scan_pick_commit", scan_ref, meta_commit, occurred_at)
    await session.commit()
    return {"scan_ref": scan_ref, "committed": True, "event_id": ev_id, "result": result}


# === 回放接口：返回 v_scan_trace 的完整链路（事件腿 + 台账腿） ===
@router.get("/scan/trace/{scan_ref}")
async def scan_trace(scan_ref: str, session: AsyncSession = Depends(get_session)) -> list[dict]:
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
