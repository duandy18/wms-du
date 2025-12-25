# app/gateway/scan_orchestrator_parse.py
from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.barcode import BarcodeResolver
from app.utils.gs1 import parse_gs1

from app.gateway.scan_orchestrator_dates import coerce_date
from app.gateway.scan_orchestrator_item_resolver import (
    resolve_item_id_from_barcode,
    resolve_item_id_from_sku,
)
from app.gateway.scan_orchestrator_tokens import parse_tokens

_BARCODE_RESOLVER = BarcodeResolver()


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
    """
    # 1) 从 barcode 字符串里解析 KV token：ITM: / QTY: / B: / PD: / EXP: / WH:
    raw = str(scan.get("barcode") or (scan.get("tokens") or {}).get("barcode") or "")
    parsed = parse_tokens(raw)

    # 2) 用 ScanRequest 顶层字段“补洞”（显式字段优先）
    for f in (
        "item_id",
        "qty",
        "task_line_id",
        "batch_code",
        "warehouse_id",
        "production_date",
        "expiry_date",
    ):
        v_scan = scan.get(f)
        v_parsed = parsed.get(f)
        if (v_parsed is None or v_parsed == "") and v_scan is not None:
            parsed[f] = v_scan

    # 3) 使用 item_barcodes 反查 item_id
    if raw and parsed.get("item_id") is None:
        item_id_from_barcode = await resolve_item_id_from_barcode(session, raw)
        if item_id_from_barcode:
            parsed["item_id"] = item_id_from_barcode

    # 4) 使用 BarcodeResolver（SKU / GTIN / 批次 / 到期）
    if raw:
        try:
            r = _BARCODE_RESOLVER.parse(raw)
        except Exception:
            r = None

        if r is not None:
            # SKU → item_id
            if getattr(r, "sku", None) and parsed.get("item_id") is None:
                iid = await resolve_item_id_from_sku(session, r.sku)  # type: ignore[arg-type]
                if iid:
                    parsed["item_id"] = iid

            # GTIN → item_id
            if getattr(r, "gtin", None) and parsed.get("item_id") is None:
                iid2 = await resolve_item_id_from_barcode(session, r.gtin)  # type: ignore[arg-type]
                if iid2:
                    parsed["item_id"] = iid2

            # 批次 / 到期
            if getattr(r, "batch", None) and not parsed.get("batch_code"):
                parsed["batch_code"] = r.batch  # type: ignore[assignment]
            if getattr(r, "expiry", None) and not parsed.get("expiry_date"):
                parsed["expiry_date"] = r.expiry  # type: ignore[assignment]

    # 5) 兜底：尝试 GS1 解析
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

    mode = (scan.get("mode") or "count").lower()
    probe = bool(scan.get("probe"))
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
