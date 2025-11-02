# app/gateway/scan_pick.py
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.stock_service import StockService
from app.utils.elog import log_error, log_event


class _ProbeRollback(Exception):
    pass


@dataclass
class ScanPickInput:
    device_id: str
    operator: str
    barcode: str  # 取货位条码：LOC:<id>
    qty: int
    item_id: Optional[int] = None
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
    row = (
        await session.execute(
            text("SELECT item_id FROM item_barcodes WHERE barcode=:bc AND active IS TRUE"),
            {"bc": barcode},
        )
    ).first()
    return int(row[0]) if row else None


async def scan_pick_commit(session: AsyncSession, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    扫码出库（拣货）：
      - 探活：保存点执行 FEFO 扣减，然后回滚，status=probe_ok
      - 真动：SCAN_REAL_PICK=1 时提交，status=ok
    支持条码驱动：tokens.item_barcode → item_id；LOC:<id> → location_id
    """
    tokens = payload.get("tokens") or {}
    if "item_id" not in payload and isinstance(tokens, dict):
        bc = tokens.get("item_barcode")
        if bc:
            resolved = await _resolve_item_id_by_barcode(session, str(bc))
            if not resolved:
                await log_error("scan_pick_error", "unknown_barcode", {"in": payload})
                raise ValueError(f"unknown_barcode: {bc}")
            payload["item_id"] = resolved

    data = ScanPickInput(
        device_id=payload.get("device_id", "unknown"),
        operator=payload.get("operator", "unknown"),
        barcode=payload.get("barcode", ""),
        qty=int(payload.get("qty", 0)),
        item_id=payload.get("item_id"),
        location_id=payload.get("location_id"),
        ctx=payload.get("ctx") or {},
    )
    if not data.item_id:
        await log_error("scan_pick_error", "missing_item_id", {"in": payload})
        raise ValueError("missing_item_id")
    if data.qty <= 0:
        await log_error("scan_pick_error", "invalid_qty", {"in": payload})
        raise ValueError("Pick qty must be positive.")

    if data.location_id is None:
        loc = _parse_loc_id(data.barcode)
        if loc is None:
            await log_error("scan_pick_error", "invalid_location_barcode", {"in": payload})
            raise ValueError("invalid_location_barcode")
        data.location_id = loc

    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ref = f"scan:{data.device_id}:{ts}:{data.barcode or 'PICK'}"

    svc = StockService()
    real_mode = os.getenv("SCAN_REAL_PICK") == "1"
    result: Dict[str, Any] = {}

    if real_mode:
        # 真动：FEFO 扣减（不指定批次，由服务层排序），允许不过期
        await svc.adjust(
            session=session,
            item_id=int(data.item_id),
            location_id=int(data.location_id),
            delta=-abs(data.qty),
            reason="PICK",
            ref=ref,
            allow_expired=False,
            allow_explicit_batch_on_outbound=False,
        )
        result = {"status": "ok", "picked": int(data.qty)}
        await session.flush()
        await session.commit()
        await log_event(
            "scan_pick_commit", ref, {"in": payload, "out": result, "ctx": data.__dict__}
        )
    else:
        try:
            async with session.begin_nested():
                await svc.adjust(
                    session=session,
                    item_id=int(data.item_id),
                    location_id=int(data.location_id),
                    delta=-abs(data.qty),
                    reason="PICK",
                    ref=ref,
                    allow_expired=False,
                    allow_explicit_batch_on_outbound=False,
                )
                raise _ProbeRollback()
        except _ProbeRollback:
            result = {"status": "probe_ok", "picked": int(data.qty)}
            await log_event(
                "scan_pick_probe", ref, {"in": payload, "out": result, "ctx": data.__dict__}
            )

    return {
        "source": "scan_pick_commit",
        "ref": ref,
        "result": result,
        "context": {
            "warehouse_id": data.warehouse_id,
            "location_id": data.location_id,
            "item_id": data.item_id,
        },
    }
