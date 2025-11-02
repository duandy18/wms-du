# app/services/scan_gateway.py
from __future__ import annotations
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone
import json
import os

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.services.audit_logger import log_event
from app.utils.gs1 import parse_gs1  # GS1 (01/10/17) 兜底解析

# 复用现有解析器；若不可用，兜底支持 LOC:/ITM:/B:
try:
    from app.services.barcode import parse_barcode as _parse_barcode  # type: ignore
except Exception:
    def _parse_barcode(code: str) -> Dict[str, Any]:
        code = (code or "").strip()
        if code.startswith("LOC:"):
            return {"location_id": int(code.split(":", 1)[1]), "raw": code}
        if code.startswith("ITM:"):
            return {"item_id": int(code.split(":", 1)[1]), "raw": code}
        if code.startswith("B:"):
            return {"batch_code": code.split(":", 1)[1], "raw": code}
        return {"raw": code}
else:
    def _parse_barcode(code: str) -> Dict[str, Any]:
        return _parse_barcode(code)

# 可选门面导入（不存在也不报错）
try:
    from app.services.putaway_service import PutawayService  # type: ignore
except Exception:
    PutawayService = None  # type: ignore

try:
    from app.services.outbound_service import OutboundService  # type: ignore
except Exception:
    OutboundService = None  # type: ignore


def _scan_dedup_key(scan: Dict[str, Any]) -> str:
    dev = (scan.get("device_id") or "dev").strip()
    bc = (scan.get("barcode") or "").strip()
    ts = (scan.get("ts") or datetime.now(timezone.utc).isoformat())[:16]  # 分钟桶
    return f"scan:{dev}:{ts}:{bc}"


# ---------- 双通道写库：engine.begin() 优先；失败回退保存点；统一使用 CAST(:meta_json AS jsonb) ----------
async def _elog(session: AsyncSession, source: str, message: str, meta: Dict[str, Any] | None = None) -> Tuple[bool, str]:
    # A) 独立连接提交
    try:
        eng = session.bind  # AsyncEngine
        if eng is not None:
            async with eng.begin() as conn:
                if meta is None:
                    await conn.execute(
                        text("INSERT INTO event_log(source, level, message, created_at) VALUES (:s,'INFO',:m,now())"),
                        {"s": source, "m": message},
                    )
                else:
                    await conn.execute(
                        text("INSERT INTO event_log(source, level, message, meta, created_at) "
                             "VALUES (:s,'INFO',:m,CAST(:meta_json AS jsonb),now())"),
                        {"s": source, "m": message, "meta_json": json.dumps(meta)},
                    )
            return True, ""
    except Exception as e:
        if os.getenv("SCAN_DEBUG") == "1":
            print("[elog-engine]", e)

    # B) 保存点回退
    try:
        async with session.begin_nested() as sp:
            if meta is None:
                await session.execute(
                    text("INSERT INTO event_log(source, level, message, created_at) VALUES (:s,'INFO',:m,now())"),
                    {"s": source, "m": message},
                )
            else:
                await session.execute(
                    text("INSERT INTO event_log(source, level, message, meta, created_at) "
                         "VALUES (:s,'INFO',:m,CAST(:meta_json AS jsonb),now())"),
                    {"s": source, "m": message, "meta_json": json.dumps(meta)},
                )
            await session.flush()
            await sp.commit()
        return True, ""
    except Exception as e2:
        try:
            await session.rollback()
        except Exception:
            pass
        if os.getenv("SCAN_DEBUG") == "1":
            print("[elog-savepoint]", e2)
        return False, str(e2)


async def _eerr(session: AsyncSession, dedup_key: str, error: str, meta: Dict[str, Any] | None = None) -> Tuple[bool, str]:
    # A) 独立连接提交
    try:
        eng = session.bind
        if eng is not None:
            async with eng.begin() as conn:
                if meta is None:
                    await conn.execute(
                        text("INSERT INTO event_error_log(dedup_key, stage, error, occurred_at, meta) "
                             "VALUES (:k,'ingest',:e,now(),'{}'::jsonb)"),
                        {"k": dedup_key, "e": error[:240]},
                    )
                else:
                    await conn.execute(
                        text("INSERT INTO event_error_log(dedup_key, stage, error, occurred_at, meta) "
                             "VALUES (:k,'ingest',:e,now(),CAST(:meta_json AS jsonb))"),
                        {"k": dedup_key, "e": error[:240], "meta_json": json.dumps(meta)},
                    )
            return True, ""
    except Exception as e:
        if os.getenv("SCAN_DEBUG") == "1":
            print("[eerr-engine]", e)

    # B) 保存点回退
    try:
        async with session.begin_nested() as sp:
            if meta is None:
                await session.execute(
                    text("INSERT INTO event_error_log(dedup_key, stage, error, occurred_at, meta) "
                         "VALUES (:k,'ingest',:e,now(),'{}'::jsonb)"),
                    {"k": dedup_key, "e": error[:240]},
                )
            else:
                await session.execute(
                    text("INSERT INTO event_error_log(dedup_key, stage, error, occurred_at, meta) "
                         "VALUES (:k,'ingest',:e,now(),CAST(:meta_json AS jsonb))"),
                    {"k": dedup_key, "e": error[:240], "meta_json": json.dumps(meta)},
                )
            await session.flush()
            await sp.commit()
        return True, ""
    except Exception as e2:
        try:
            await session.rollback()
        except Exception:
            pass
        if os.getenv("SCAN_DEBUG") == "1":
            print("[eerr-savepoint]", e2)
        return False, str(e2)


async def _probe_in_savepoint(session: AsyncSession, fn, *args, **kwargs) -> Dict[str, Any]:
    try:
        async with session.begin_nested() as sp:
            await fn(*args, **kwargs)
            await sp.rollback()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:240]}


async def ingest(scan: Dict[str, Any], session: Optional[AsyncSession]) -> Dict[str, Any]:
    """
    扫码网关：
      - 解析 → 校验 → 留痕（双通道写库）；
      - 按 mode 路由（putaway/pick/count）：
         * putaway: SCAN_REAL_PUTAWAY=1 时执行真动作（对齐 PutawayService.putaway）；
         * 否则保存点探活；
      - 返回证据与错误，便于测试与排障。
    返回：
      { ok, parsed, ctx, dedup_key, evidence: [{source, db, err?}], errors: [{stage, error, db, err?}] }
    """
    dedup = _scan_dedup_key(scan)
    evidence: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    if session is None:
        return {"ok": False, "error": "ScanGateway.ingest requires an AsyncSession",
                "dedup_key": dedup, "evidence": evidence, "errors": errors}

    # 1) 解析 + GS1 兜底 + 载荷兜底
    parsed = _parse_barcode(scan.get("barcode", "")) or {}
    if not (parsed.get("batch_code") or parsed.get("expiry") or parsed.get("item_id")):
        gs1 = parse_gs1(scan.get("barcode", ""))
        if gs1:
            parsed.update(gs1)
    if not parsed.get("item_id") and scan.get("item_id") is not None:
        try:
            parsed["item_id"] = int(scan["item_id"])
        except Exception:
            pass
    if not parsed.get("location_id") and scan.get("location_id") is not None:
        try:
            parsed["location_id"] = int(scan["location_id"])
        except Exception:
            pass

    qty = int(scan.get("qty") or 1)
    ctx = {
        "warehouse_id": scan.get("ctx", {}).get("warehouse_id"),
        "location_hint": scan.get("ctx", {}).get("location_hint"),
        "mode": (scan.get("mode") or "count").lower(),
        "device_id": scan.get("device_id"),
        "operator": scan.get("operator"),
        "qty": qty,
    }

    # 2) 基本校验
    try:
        if parsed.get("location_id") is not None:
            found = (await session.execute(
                text("SELECT 1 FROM locations WHERE id=:i"),
                {"i": int(parsed["location_id"])},
            )).first()
            if not found:
                raise ValueError(f"Unknown location_id: {parsed['location_id']}")
    except Exception as e:
        ok, err = await _eerr(session, dedup, str(e), {"scan": scan})
        item = {"stage": "validate", "error": str(e), "db": ok}
        if not ok:
            item["err"] = err
        errors.append(item)
        try:
            log_event("scan_error", dedup, extra={"error": str(e), "scan": scan})
        except Exception:
            pass
        return {"ok": False, "error": str(e), "dedup_key": dedup, "evidence": evidence, "errors": errors}

    # 3) 留痕：scan_ingest / scan_route
    try:
        log_event("scan_ingest", dedup, extra={"parsed": parsed, "ctx": ctx})
    except Exception:
        pass
    ok_ing, err_ing = await _elog(session, "scan_ingest", dedup, {"parsed": parsed, "ctx": ctx})
    ev = {"source": "scan_ingest", "db": ok_ing}
    if not ok_ing:
        ev["err"] = err_ing
    evidence.append(ev)

    route = ctx["mode"]
    try:
        log_event("scan_route", dedup, extra={"route": route})
    except Exception:
        pass
    ok_route, err_route = await _elog(session, "scan_route", dedup, {"route": route, "parsed": parsed, "ctx": ctx})
    ev = {"source": "scan_route", "db": ok_route}
    if not ok_route:
        ev["err"] = err_route
    evidence.append(ev)

    # 4) 分支
    if route == "putaway":
        # 路径证据
        ok_path, err_path = await _elog(session, "scan_putaway_path", dedup, {"line": {
            "item_id": int(parsed.get("item_id") or 0),
            "location_id": int(parsed.get("location_id") or 0),
            "qty": qty
        }})
        ev = {"source": "scan_putaway_path", "db": ok_path}
        if not ok_path:
            ev["err"] = err_path
        evidence.append(ev)

        # 计算来源位（优先 scan.from_location_id → ctx.stage_location_id → env.SCAN_STAGE_LOCATION_ID）
        from_loc = None
        try:
            if isinstance(scan, dict) and scan.get("from_location_id") is not None:
                from_loc = int(scan["from_location_id"])
            elif ctx.get("stage_location_id") is not None:
                from_loc = int(ctx["stage_location_id"])
            elif os.getenv("SCAN_STAGE_LOCATION_ID"):
                from_loc = int(os.getenv("SCAN_STAGE_LOCATION_ID"))  # noqa
        except Exception:
            from_loc = None

        if from_loc is None:
            ok_e, err_e = await _elog(session, "scan_route_probe_error", dedup, {
                "route": "putaway",
                "error": "missing from_location_id (payload.from_location_id / ctx.stage_location_id / SCAN_STAGE_LOCATION_ID)"
            })
            evidence.append({"source": "scan_route_probe_error", "db": ok_e, **({"err": err_e} if not ok_e else {})})

        elif PutawayService is None:
            ok_e, err_e = await _elog(session, "scan_route_probe_error", dedup,
                                      {"route": "putaway", "error": "PutawayService not available"})
            evidence.append({"source": "scan_route_probe_error", "db": ok_e, **({"err": err_e} if not ok_e else {})})

        else:
            # 先从源位查询 batch_code（与正式口径对齐）
            bc_row = (await session.execute(text("""
                SELECT batch_code
                  FROM stocks
                 WHERE item_id=:i
                   AND warehouse_id=:w
                   AND location_id=:from_loc
                 ORDER BY qty DESC, id DESC
                 LIMIT 1
            """), {"i": int(parsed.get("item_id") or 0), "w": int(ctx.get("warehouse_id") or 0), "from_loc": int(from_loc)})).first()
            if not bc_row or not bc_row[0]:
                ok_e, err_e = await _elog(session, "scan_route_probe_error", dedup, {
                    "route": "putaway",
                    "error": "missing batch_code on source location; cannot upsert without batch dimension"
                })
                evidence.append({"source": "scan_route_probe_error", "db": ok_e, **({"err": err_e} if not ok_e else {})})
            else:
                batch_code = str(bc_row[0])

                line_payload = {
                    "item_id": int(parsed.get("item_id") or 0),
                    "from_location_id": int(from_loc),
                    "to_location_id": int(parsed["location_id"]),
                    "qty": qty,
                    "warehouse_id": int(ctx.get("warehouse_id") or 0),
                    "batch_code": batch_code,
                    "ref": f"SCAN-PUTAWAY:{dedup}",
                    "ref_line": 1,
                    "occurred_at": None,
                    "commit": False,
                }

                if os.getenv("SCAN_REAL_PUTAWAY") == "1":
                    try:
                        res = await PutawayService.putaway(  # type: ignore[attr-defined]
                            session,
                            **line_payload,
                        )
                        ok_c, err_c = await _elog(session, "scan_putaway_commit", dedup,
                                                  {"route": "putaway", "result": res})
                        evidence.append({"source": "scan_putaway_commit", "db": ok_c, **({"err": err_c} if not ok_c else {})})
                    except Exception as e:
                        ok_e1, err1 = await _eerr(session, dedup, str(e), {"route": "putaway", "hint": "PutawayService.putaway"})
                        ok_e2, err2 = await _elog(session, "scan_route_probe_error", dedup,
                                                  {"route": "putaway", "error": str(e)[:240]})
                        errors.append({"stage": "putaway", "error": str(e), "db": ok_e1, **({"err": err1} if not ok_e1 else {})})
                        evidence.append({"source": "scan_route_probe_error", "db": ok_e2, **({"err": err2} if not ok_e2 else {})})
                else:
                    async def _call():
                        await PutawayService.putaway(  # type: ignore[attr-defined]
                            session,
                            **line_payload,
                        )
                    pr = await _probe_in_savepoint(session, _call)
                    if not pr["ok"]:
                        ok_e, err_e = await _elog(session, "scan_route_probe_error", dedup,
                                                  {"route": "putaway", "error": pr["error"]})
                        evidence.append({"source": "scan_route_probe_error", "db": ok_e, **({"err": err_e} if not ok_e else {})})

    elif route == "pick":
        if OutboundService is not None:
            line = {
                "item_id": int(parsed.get("item_id") or 0),
                "location_id": int(parsed.get("location_id") or 0),
                "qty": qty,
            }

            async def _call():
                await OutboundService.commit(  # type: ignore[attr-defined]
                    session,
                    platform="scan",
                    shop_id=None,
                    ref=f"SCAN-PICK:{dedup}",
                    lines=[line],
                    refresh_visible=False,
                )

            pr = await _probe_in_savepoint(session, _call)
            if not pr["ok"]:
                ok_e, err_e = await _elog(session, "scan_route_probe_error", dedup,
                                          {"route": "pick", "error": pr["error"]})
                evidence.append({"source": "scan_route_probe_error", "db": ok_e, **({"err": err_e} if not ok_e else {})})

    elif route == "count":
        ok_cd, err_cd = await _elog(session, "scan_count_draft", dedup, {"parsed": parsed, "ctx": ctx})
        evidence.append({"source": "scan_count_draft", "db": ok_cd, **({"err": err_cd} if not ok_cd else {})})

    return {
        "ok": True,
        "parsed": parsed,
        "ctx": ctx,
        "dedup_key": dedup,
        "evidence": evidence,
        "errors": errors,
    }
