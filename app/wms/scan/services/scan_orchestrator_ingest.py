# app/wms/scan/services/scan_orchestrator_ingest.py
from __future__ import annotations

from datetime import timezone
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditWriter

from app.wms.scan.services.scan_orchestrator_parse import parse_scan
from app.wms.scan.services.scan_orchestrator_refs import normalize_ref
from app.wms.scan.services.scan_orchestrator_tokens import ALLOWED_SCAN_MODES

from app.wms.scan.services.scan_orchestrator_ingest_count import run_count_flow
from app.wms.scan.services.scan_orchestrator_ingest_receive import run_receive_flow
from app.wms.scan.services.scan_orchestrator_ingest_pick import run_pick_flow

UTC = timezone.utc
AUDIT = AuditWriter()


def _get_or_create_scan_session_id(scan: Dict[str, Any]) -> str:
    """
    方案 B（事件级幂等）：
    - 优先使用 scan.ctx.scan_session_id（客户端/调用方可在重试时复用，以命中幂等）
    - 若缺失则生成一个 UUID（每次调用唯一，避免“分钟 ref”撞车）
    """
    ctx = scan.get("ctx")
    if isinstance(ctx, dict):
        v = ctx.get("scan_session_id")
        if v is not None:
            s = str(v).strip()
            if s:
                return s

    # 生成新的 session id，并回写到 ctx（便于下游/日志/审计统一）
    sid = uuid.uuid4().hex
    if ctx is None:
        scan["ctx"] = {"scan_session_id": sid}
    elif isinstance(ctx, dict):
        ctx["scan_session_id"] = sid
    else:
        # ctx 非 dict：不强行覆盖类型，只保证返回 sid
        pass
    return sid


def _build_scan_ref(*, mode: str, scan_session_id: str) -> str:
    # 事件级 ref：稳定、可幂等、不会因分钟粒度导致误幂等
    # 形如：scan:receive:dev:<scan_session_id>
    return f"scan:{str(mode).strip().lower()}:dev:{scan_session_id}"


def _coerce_optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    return int(value)


def _build_qty_base(
    *,
    mode: str,
    qty: int,
    ratio_to_base: Optional[int],
) -> Optional[int]:
    """
    仅 receive / pick 进入“执行单位基础化”：
    - qty：仍代表输入单位数量
    - qty_base：代表真正下送 handler 的 base qty

    count 暂不改语义：
    - count_handler 的 actual 是“盘点后的绝对量”，不是增量
    - 因此这里先返回 None，不参与 count 执行
    """
    if mode not in {"receive", "pick"}:
        return None

    ratio = int(ratio_to_base or 1)
    if ratio <= 0:
        raise ValueError("ratio_to_base 必须 >= 1")

    return int(qty) * int(ratio)


def _attach_scan_passthrough(
    result: Dict[str, Any],
    *,
    item_uom_id: Optional[int],
    ratio_to_base: Optional[int],
    qty_base: Optional[int],
) -> Dict[str, Any]:
    out = dict(result)
    out["item_uom_id"] = item_uom_id
    out["ratio_to_base"] = ratio_to_base
    out["qty_base"] = qty_base
    return out


async def ingest(scan: Dict[str, Any], session: Optional[AsyncSession]) -> Dict[str, Any]:
    """
    v2 扫描编排器（receive / pick / count；历史 putaway 已下线）：
      - 解析 ScanRequest / barcode / GS1 / item_barcodes / BarcodeResolver
      - probe 模式：
          * receive / count：跑 handler，但不提交 Tx
          * pick：只做解析，不调用 handle_pick，不动账（条码→item_id 解析服务）
      - commit 模式：TxManager + 对应 handler
      - 统一返回结构（ok/committed/scan_ref/event_id/evidence/errors）

    幂等策略（方案 B）：
      - ref = scan:{mode}:dev:{scan_session_id}
      - scan_session_id 来自 scan.ctx.scan_session_id（重试复用）；否则后端生成 UUID
    """
    # 即使没有 session，也先生成一个事件级 scan_ref 作为回显（便于调用方带着 ref 重试）
    scan_mut: Dict[str, Any] = dict(scan or {})
    mode_guess = str(scan_mut.get("mode") or "").strip() or "unknown"
    scan_session_id = _get_or_create_scan_session_id(scan_mut)
    dummy_ref = _build_scan_ref(mode=mode_guess, scan_session_id=scan_session_id)

    if session is None:
        return {
            "ok": False,
            "committed": False,
            "scan_ref": dummy_ref,
            "event_id": None,
            "source": None,
            "evidence": [],
            "errors": [{"stage": "ingest", "error": "missing session"}],
            "item_id": None,
            "item_uom_id": None,
            "ratio_to_base": None,
            "qty_base": None,
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
    ) = await parse_scan(scan_mut, session)

    item_uom_id = _coerce_optional_int(parsed.get("item_uom_id"))
    ratio_to_base = _coerce_optional_int(parsed.get("ratio_to_base"))
    qty_base = _build_qty_base(
        mode=mode,
        qty=int(qty),
        ratio_to_base=ratio_to_base,
    )

    # ✅ 关键：确保 scan_ref 一定含 mode（哪怕调用方没传、parse_scan 推导了）
    scan_with_mode: Dict[str, Any] = dict(scan_mut or {})
    scan_with_mode["mode"] = mode

    # ✅ 方案 B：事件级 scan_session_id（重试复用）
    scan_session_id = _get_or_create_scan_session_id(scan_with_mode)

    # ✅ 生成事件级 scan_ref，再走 normalize_ref 做统一规范化
    scan_ref_raw = _build_scan_ref(mode=mode, scan_session_id=scan_session_id)
    scan_ref_norm = await normalize_ref(session, scan_ref_raw)

    evidence: List[Dict[str, Any]] = []

    if mode not in ALLOWED_SCAN_MODES:
        ev = await AUDIT.other(session, scan_ref_norm)
        # 这里不再把所有非法 mode 误报为 putaway；明确为 unsupported_mode
        return {
            "ok": False,
            "committed": False,
            "scan_ref": scan_ref_norm,
            "event_id": ev,
            "source": "scan_feature_disabled",
            "evidence": [{"source": "scan_feature_disabled", "db": True}],
            "errors": [{"stage": "ingest", "error": f"FEATURE_DISABLED: unsupported_mode:{mode}"}],
            "item_id": item_id,
            "item_uom_id": item_uom_id,
            "ratio_to_base": ratio_to_base,
            "qty_base": qty_base,
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
            if not probe:
                ev = await AUDIT.other(session, scan_ref_norm)
                return {
                    "ok": False,
                    "committed": False,
                    "scan_ref": scan_ref_norm,
                    "event_id": ev,
                    "source": "scan_feature_disabled",
                    "evidence": [{"source": "scan_feature_disabled", "db": True}],
                    "errors": [{"stage": "ingest", "error": "FEATURE_DISABLED: count_commit_disabled_use_/count"}],
                    "item_id": item_id,
                    "item_uom_id": item_uom_id,
                    "ratio_to_base": ratio_to_base,
                    "qty_base": qty_base,
                }
            result = await run_count_flow(
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
            return _attach_scan_passthrough(
                result,
                item_uom_id=item_uom_id,
                ratio_to_base=ratio_to_base,
                qty_base=qty_base,
            )

        if mode == "receive":
            exec_qty = int(qty_base if qty_base is not None else qty)
            result = await run_receive_flow(
                session=session,
                audit=AUDIT,
                scan_ref_norm=scan_ref_norm,
                probe=probe,
                base_kwargs=base_kwargs,
                qty=exec_qty,
                item_id=item_id,
                evidence=evidence,
            )
            return _attach_scan_passthrough(
                result,
                item_uom_id=item_uom_id,
                ratio_to_base=ratio_to_base,
                qty_base=exec_qty,
            )

        # pick
        if not probe:
            ev = await AUDIT.other(session, scan_ref_norm)
            return {
                "ok": False,
                "committed": False,
                "scan_ref": scan_ref_norm,
                "event_id": ev,
                "source": "scan_feature_disabled",
                "evidence": [{"source": "scan_feature_disabled", "db": True}],
                "errors": [{"stage": "ingest", "error": "FEATURE_DISABLED: pick_commit_disabled_use_/pick-tasks/{task_id}/scan"}],
                "item_id": item_id,
                "item_uom_id": item_uom_id,
                "ratio_to_base": ratio_to_base,
                "qty_base": qty_base,
            }

        exec_qty = int(qty_base if qty_base is not None else qty)
        result = await run_pick_flow(
            session=session,
            audit=AUDIT,
            scan_ref_norm=scan_ref_norm,
            probe=probe,
            parsed=parsed,
            base_kwargs=base_kwargs,
            qty=exec_qty,
            item_id=item_id,
            wh_id=wh_id,
            batch_code=batch_code,
            production_date=production_date,
            expiry_date=expiry_date,
            evidence=evidence,
        )
        return _attach_scan_passthrough(
            result,
            item_uom_id=item_uom_id,
            ratio_to_base=ratio_to_base,
            qty_base=exec_qty,
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
            "item_uom_id": item_uom_id,
            "ratio_to_base": ratio_to_base,
            "qty_base": qty_base,
        }
