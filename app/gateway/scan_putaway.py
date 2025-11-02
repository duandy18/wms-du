# app/gateway/scan_putaway.py
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.stock_service import StockService
from app.utils.elog import log_error, log_event


class _ProbeRollback(Exception):
    """用于保存点回滚（探活）。"""

    pass


@dataclass
class ScanPutawayInput:
    device_id: str
    operator: str
    barcode: str  # 目标库位条码：LOC:<id>
    item_id: int
    qty: int
    from_location_id: Optional[int] = None
    to_location_id: Optional[int] = None
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


async def _select_source_batches(
    session: AsyncSession, item_id: int, wh: int, src_loc: int
) -> List[Tuple[str, int]]:
    """
    选出源位可用批次：[(batch_code, qty), ...]
    优先按有到期日的 FEFO，其次按批次代码排序。
    """
    sql = text(
        """
        SELECT s.batch_code,
               COALESCE(s.qty,0)::bigint AS qty
        FROM stocks s
        LEFT JOIN batches b
          ON b.item_id=s.item_id AND b.warehouse_id=s.warehouse_id
         AND b.location_id=s.location_id AND b.batch_code=s.batch_code
        WHERE s.item_id=:iid AND s.warehouse_id=:wid AND s.location_id=:loc AND s.qty>0
        ORDER BY b.expire_at NULLS LAST, s.batch_code
        """
    )
    rows = await session.execute(sql, {"iid": item_id, "wid": wh, "loc": src_loc})
    out: List[Tuple[str, int]] = []
    for r in rows:
        out.append((str(r[0]), int(r[1])))
    return out


async def scan_putaway_commit(session: AsyncSession, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    扫码上架：从源位（默认 SCAN_STAGE_LOCATION_ID）把同一 item 的批次，搬到目标库位（barcode=LOC:*）。
    - 探活：保存点执行、随后回滚，返回 status=probe_ok
    - 真动：环境变量 SCAN_REAL_PUTAWAY=1 时提交，返回 status=ok
    """
    # 条码驱动：若未给 item_id，则从 tokens.item_barcode 解析
    tokens = payload.get("tokens") or {}
    if "item_id" not in payload and isinstance(tokens, dict):
        bc = tokens.get("item_barcode")
        if bc:
            resolved = await _resolve_item_id_by_barcode(session, str(bc))
            if not resolved:
                await log_error("scan_putaway_error", "unknown_barcode", {"in": payload})
                raise ValueError(f"unknown_barcode: {bc}")
            payload["item_id"] = resolved

    data = ScanPutawayInput(
        device_id=payload.get("device_id", "unknown"),
        operator=payload.get("operator", "unknown"),
        barcode=payload.get("barcode", ""),
        item_id=int(payload["item_id"]),
        qty=int(payload.get("qty", 0)),
        from_location_id=payload.get("from_location_id"),
        to_location_id=payload.get("to_location_id"),
        ctx=payload.get("ctx") or {},
    )
    if data.qty <= 0:
        await log_error("scan_putaway_error", "invalid_qty", {"in": payload})
        raise ValueError("Putaway qty must be positive.")

    # 解析目标库位
    if data.to_location_id is None:
        dst = _parse_loc_id(data.barcode)
        if dst is None:
            await log_error(
                "scan_putaway_error", "invalid_target_location_barcode", {"in": payload}
            )
            raise ValueError("invalid_target_location_barcode")
        data.to_location_id = dst

    # 源位：优先载荷/ctx，其次环境变量
    if data.from_location_id is None:
        stage = os.getenv("SCAN_STAGE_LOCATION_ID")
        if stage and stage.isdigit():
            data.from_location_id = int(stage)
        else:
            await log_error("scan_putaway_error", "missing_stage_location_id", {"in": payload})
            raise ValueError("missing_stage_location_id")

    wh = data.warehouse_id
    svc = StockService()

    # 选源位批次（FEFO优先）
    src_batches = await _select_source_batches(session, data.item_id, wh, data.from_location_id)
    if not src_batches:
        await log_error("scan_putaway_error", "no_source_stock_for_item", {"in": payload})
        raise ValueError("no_source_stock_for_item")

    # 构造证据链
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ref_base = f"scan:{data.device_id}:{ts}:{data.barcode or 'PUTAWAY'}"

    # 拆腿搬运
    def _moves_plan(qty: int) -> List[Tuple[str, int]]:
        plan: List[Tuple[str, int]] = []
        remain = qty
        for bc, q in src_batches:
            if remain <= 0:
                break
            take = min(remain, q)
            plan.append((bc, take))
            remain -= take
        if remain > 0:
            raise ValueError("insufficient_source_qty")
        return plan

    plan = _moves_plan(data.qty)

    real_mode = os.getenv("SCAN_REAL_PUTAWAY") == "1"
    moves: List[Dict[str, Any]] = []

    async def _do_moves() -> None:
        leg = 0
        for batch_code, q in plan:
            leg += 1
            ref = f"{ref_base}#L{leg}"
            # 源位扣
            await svc.adjust(
                session=session,
                item_id=data.item_id,
                location_id=data.from_location_id,  # 源
                delta=-q,
                reason="PUTAWAY",
                ref=f"{ref}:SRC",
                batch_code=batch_code,
                allow_explicit_batch_on_outbound=True,  # 定向批次，避免 FEFO 再次重排
            )
            # 目标位加（同批）
            await svc.adjust(
                session=session,
                item_id=data.item_id,
                location_id=data.to_location_id,  # 目标
                delta=+q,
                reason="PUTAWAY",
                ref=f"{ref}:DST",
                batch_code=batch_code,
            )
            moves.append({"batch_code": batch_code, "moved": q})

    if real_mode:
        await _do_moves()
        status = "ok"
        # 提交，确保双腿台账与库存落库
        await session.flush()
        await session.commit()
        await log_event(
            "scan_putaway_commit", ref_base, {"in": payload, "moves": moves, "ctx": data.__dict__}
        )
    else:
        try:
            async with session.begin_nested():
                await _do_moves()
                raise _ProbeRollback()
        except _ProbeRollback:
            status = "probe_ok"
            await log_event(
                "scan_putaway_probe",
                ref_base,
                {"in": payload, "moves": moves, "ctx": data.__dict__},
            )

    return {
        "source": "scan_putaway_commit",
        "result": {
            "status": status,
            "moved_total": data.qty,
            "moves": moves,  # [{batch_code, moved}]
        },
        "context": {
            "warehouse_id": wh,
            "from_location_id": data.from_location_id,
            "to_location_id": data.to_location_id,
            "item_id": data.item_id,
        },
    }
