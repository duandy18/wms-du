# app/wms/scan/services/scan_orchestrator_parse.py
from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.shared.services.barcode import BarcodeResolver
from app.utils.gs1 import parse_gs1

from app.wms.scan.services.scan_orchestrator_dates import coerce_date
from app.wms.scan.services.scan_orchestrator_item_resolver import (
    probe_item_from_barcode,
    resolve_item_id_from_sku,
)
from app.wms.scan.services.scan_orchestrator_tokens import parse_tokens

_BARCODE_RESOLVER = BarcodeResolver()


def _apply_barcode_probe(parsed: Dict[str, Any], resolved: object) -> None:
    """
    把 PMS public barcode probe 的 richer 结果并入 parsed。
    当前阶段只做“写入 parsed”，不改变 parse_scan 的返回 tuple 形状。
    """
    item_id = getattr(resolved, "item_id", None)
    item_uom_id = getattr(resolved, "item_uom_id", None)
    ratio_to_base = getattr(resolved, "ratio_to_base", None)

    if item_id is not None and not parsed.get("item_id"):
        parsed["item_id"] = int(item_id)

    if item_uom_id is not None and not parsed.get("item_uom_id"):
        parsed["item_uom_id"] = int(item_uom_id)

    if ratio_to_base is not None and not parsed.get("ratio_to_base"):
        parsed["ratio_to_base"] = int(ratio_to_base)


async def parse_scan(
    scan: Dict[str, Any],
    session: AsyncSession,
) -> Tuple[
    Dict[str, Any],
    str,
    bool,
    int,
    int,
    Optional[str],
    int,
    Optional[date],
    Optional[date],
]:
    """
    统一解析 /scan 请求，返回：
      parsed, mode, probe, qty, item_id, batch_code, warehouse_id,
      production_date(date|None), expiry_date(date|None)

    /scan 已收口为 pick probe 工具层：
    - 只负责商品 / 包装识别
    - 不再承担 receive / count 主链语义
    - 不再保留 receive_probe_light 这类过渡逻辑
    """
    mode = str(scan.get("mode") or "pick").lower()
    probe = bool(scan.get("probe", True))

    raw = str(scan.get("barcode") or (scan.get("tokens") or {}).get("barcode") or "")
    parsed = parse_tokens(raw)

    for f in (
        "item_id",
        "qty",
        "task_line_id",
        "batch_code",
        "lot_code",
        "warehouse_id",
        "production_date",
        "expiry_date",
    ):
        v_scan = scan.get(f)
        v_parsed = parsed.get(f)
        if (v_parsed is None or v_parsed == "") and v_scan is not None:
            parsed[f] = v_scan

    if not parsed.get("batch_code") and parsed.get("lot_code"):
        parsed["batch_code"] = parsed.get("lot_code")

    if raw and parsed.get("item_id") is None:
        resolved = await probe_item_from_barcode(session, raw)
        if resolved is not None:
            _apply_barcode_probe(parsed, resolved)

    if raw:
        try:
            r = _BARCODE_RESOLVER.parse(raw)
        except Exception:
            r = None

        if r is not None:
            if getattr(r, "sku", None) and parsed.get("item_id") is None:
                iid = await resolve_item_id_from_sku(session, r.sku)  # type: ignore[arg-type]
                if iid:
                    parsed["item_id"] = iid

            if getattr(r, "gtin", None) and parsed.get("item_id") is None:
                resolved_gtin = await probe_item_from_barcode(session, r.gtin)  # type: ignore[arg-type]
                if resolved_gtin is not None:
                    _apply_barcode_probe(parsed, resolved_gtin)

            if getattr(r, "batch", None) and not parsed.get("batch_code"):
                parsed["batch_code"] = r.batch  # type: ignore[assignment]
            if getattr(r, "expiry", None) and not parsed.get("expiry_date"):
                parsed["expiry_date"] = r.expiry  # type: ignore[assignment]

        if raw and not (parsed.get("item_id") or parsed.get("batch_code") or parsed.get("expiry_date")):
            gs1 = parse_gs1(raw)
            if gs1:
                if "batch" in gs1 and "batch_code" not in parsed:
                    parsed["batch_code"] = gs1["batch"]
                if "expiry" in gs1 and "expiry_date" not in parsed:
                    parsed["expiry_date"] = gs1["expiry"]
                for k in ("item_id", "production_date", "expiry_date", "batch_code"):
                    if gs1.get(k) and not parsed.get(k):
                        parsed[k] = gs1[k]

    qty = int(parsed.get("qty") or scan.get("qty") or 1)
    item_id = int(parsed.get("item_id") or 0)
    batch_code = parsed.get("batch_code")
    wh_id = int(parsed.get("warehouse_id") or scan.get("warehouse_id") or 1)

    production_date = coerce_date(parsed.get("production_date"))
    expiry_date = coerce_date(parsed.get("expiry_date"))

    return (
        parsed,
        mode,
        probe,
        qty,
        item_id,
        batch_code,
        wh_id,
        production_date,
        expiry_date,
    )
