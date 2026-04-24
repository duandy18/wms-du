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

    sid = uuid.uuid4().hex
    if ctx is None:
        scan["ctx"] = {"scan_session_id": sid}
    elif isinstance(ctx, dict):
        ctx["scan_session_id"] = sid
    else:
        pass
    return sid


def _build_scan_ref(*, mode: str, scan_session_id: str) -> str:
    # 事件级 ref：稳定、可幂等
    # 形如：scan:pick:dev:<scan_session_id>
    return f"scan:{str(mode).strip().lower()}:dev:{scan_session_id}"


def _coerce_optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    return int(value)


def _build_qty_base(
    *,
    qty: int,
    ratio_to_base: Optional[int],
) -> int:
    """
    pick probe 仍保留输入单位→base 的投影，
    仅用于返回识别结果，不承担库存执行语义。
    """
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
    /scan 已收口为 pick probe 工具层：

    - 仅解析条码并返回商品 / 包装识别结果
    - 不再承接 receive / count 主链
    - 不再承担任何 commit 语义
    """
    scan_mut: Dict[str, Any] = dict(scan or {})
    mode_guess = str(scan_mut.get("mode") or "").strip() or "pick"
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
        qty=int(qty),
        ratio_to_base=ratio_to_base,
    )

    scan_with_mode: Dict[str, Any] = dict(scan_mut or {})
    scan_with_mode["mode"] = mode

    scan_session_id = _get_or_create_scan_session_id(scan_with_mode)
    scan_ref_raw = _build_scan_ref(mode=mode, scan_session_id=scan_session_id)
    scan_ref_norm = await normalize_ref(session, scan_ref_raw)

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
        if not probe:
            ev = await AUDIT.other(session, scan_ref_norm)
            return {
                "ok": False,
                "committed": False,
                "scan_ref": scan_ref_norm,
                "event_id": ev,
                "source": "scan_feature_disabled",
                "evidence": [{"source": "scan_feature_disabled", "db": True}],
                "errors": [{"stage": "ingest", "error": "FEATURE_DISABLED: scan_is_probe_only_use_/orders/{platform}/{shop_id}/{ext_order_no}/pick"}],
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
