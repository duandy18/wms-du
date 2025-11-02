# app/gateway/scan_count.py
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.stock_service import StockService
from app.utils.elog import log_event, log_error


class _ProbeRollback(Exception):
    pass


@dataclass
class ScanCountInput:
    device_id: str
    operator: str
    barcode: str            # 被盘点库位：LOC:<id>
    item_id: Optional[int]
    counted_qty: float
    location_id: Optional[int] = None
    ctx: Optional[Dict[str, Any]] = None

    @property
    def warehouse_id(self) -> int:
        if self.ctx and isinstance(self.ctx, dict):
            wid = self.ctx.get("warehouse_id")
            if isinstance(wid, int) and wid > 0:
                return wid
        return 1


def _parse_loc_id(barcode: str) -> Optional[int]:
    if not barcode:
        return None
    s = barcode.strip().upper()
    if s.startswith("LOC:"):
        try:
            return int(s.split(":", 1)[1])
        except Exception:
            return None
    return None


async def _resolve_item_id_by_barcode(session: AsyncSession, barcode: str) -> Optional[int]:
    if not barcode:
        return None
    row = (await session.execute(
        text("SELECT item_id FROM item_barcodes WHERE barcode=:bc AND active IS TRUE"),
        {"bc": barcode},
    )).first()
    return int(row[0]) if row else None


async def scan_count_commit(session: AsyncSession, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    扫码盘点：
      - 探活：只做差额计算与校验，不改动（保存点回滚），status=probe_ok
      - 真动：调用 Reconcile 差额落账，status=ok
    默认由网关直接调用 StockService.reconcile_inventory()
    """
    tokens = payload.get("tokens") or {}
    if "item_id" not in payload and isinstance(tokens, dict):
        bc = tokens.get("item_barcode")
        if bc:
            resolved = await _resolve_item_id_by_barcode(session, str(bc))
            if not resolved:
                await log_error("scan_count_error", "unknown_barcode", {"in": payload})
                raise ValueError(f"unknown_barcode: {bc}")
            payload["item_id"] = resolved

    data = ScanCountInput(
        device_id=payload.get("device_id", "unknown"),
        operator=payload.get("operator", "unknown"),
        barcode=payload.get("barcode", ""),
        item_id=payload.get("item_id"),
        counted_qty=float(payload.get("qty", 0)),
        location_id=payload.get("location_id"),
        ctx=payload.get("ctx") or {},
    )
    if not data.item_id:
        await log_error("scan_count_error", "missing_item_id", {"in": payload})
        raise ValueError("missing_item_id")
    if data.counted_qty < 0:
        await log_error("scan_count_error", "invalid_qty", {"in": payload})
        raise ValueError("Count qty must be non-negative.")

    if data.location_id is None:
        loc = _parse_loc_id(data.barcode)
        if loc is None:
            await log_error("scan_count_error", "invalid_location_barcode", {"in": payload})
            raise ValueError("invalid_location_barcode")
        data.location_id = loc

    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ref = f"scan:{data.device_id}:{ts}:{data.barcode or 'COUNT'}"

    svc = StockService()
    real_mode = os.getenv("SCAN_REAL_COUNT") == "1"
    result: Dict[str, Any] = {}

    if real_mode:
        # 真动：按差额进行 reconcile（apply=True）
        out = await svc.reconcile_inventory(
            session=session,
            item_id=int(data.item_id),
            location_id=int(data.location_id),
            counted_qty=float(data.counted_qty),
            apply=True,
            ref=ref,
        )
        result = {"status": "ok", "reconciled": True, "diff": out.get("diff")}
        await session.flush()
        await session.commit()
        await log_event("scan_count_commit", ref, {"in": payload, "out": result, "ctx": data.__dict__})
    else:
        # 探活：试算差额，不落账（保存点回滚）
        try:
            async with session.begin_nested():
                out = await svc.reconcile_inventory(
                    session=session,
                    item_id=int(data.item_id),
                    location_id=int(data.location_id),
                    counted_qty=float(data.counted_qty),
                    apply=False,
                    ref=ref,
                )
                # out 里一般会返回 diff，可拿来显示
                result = {"status": "probe_ok", "reconciled": False, "diff": out.get("diff")}
                raise _ProbeRollback()
        except _ProbeRollback:
            await log_event("scan_count_probe", ref, {"in": payload, "out": result, "ctx": data.__dict__})

    return {
        "source": "scan_count_commit",
        "ref": ref,
        "result": result,
        "context": {
            "warehouse_id": data.warehouse_id,
            "location_id": data.location_id,
            "item_id": data.item_id,
        },
    }
