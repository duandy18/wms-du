# app/gateway/scan_receive.py
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.stock_service import StockService
from app.utils.elog import log_event, log_error  # 独立连接写 event_log / event_error_log


class _ProbeRollback(Exception):
    """内部异常：用于在保存点中回滚真动作（探活模式）。"""
    pass


@dataclass
class ScanReceiveInput:
    device_id: str
    operator: str
    barcode: str
    item_id: int
    qty: int
    location_id: Optional[int] = None
    batch_code: Optional[str] = None
    expire_at: Optional[datetime] = None  # 允许透传，但当前不直接传给门面
    ctx: Optional[Dict[str, Any]] = None

    @property
    def warehouse_id(self) -> int:
        if self.ctx and isinstance(self.ctx, dict):
            wid = self.ctx.get("warehouse_id")
            if isinstance(wid, int) and wid > 0:
                return wid
        return 1


def _parse_location_from_barcode(barcode: str) -> Optional[int]:
    """约定：LOC:123 形式解析为 location_id=123。"""
    if not barcode:
        return None
    token = barcode.strip().upper()
    if token.startswith("LOC:"):
        try:
            return int(token.split(":", 1)[1])
        except Exception:
            return None
    return None


def _autogen_batch_code(item_id: int) -> str:
    """若缺批次则自动生成：AUTO-<item_id>-YYYYMMDD。"""
    return f"AUTO-{item_id}-{datetime.now(tz=timezone.utc).strftime('%Y%m%d')}"


async def _resolve_item_id_by_barcode(session: AsyncSession, barcode: str) -> Optional[int]:
    """从 item_barcodes 解析条码到 item_id；找不到返回 None。"""
    if not barcode:
        return None
    row = (await session.execute(
        text("SELECT item_id FROM item_barcodes WHERE barcode=:bc AND active IS TRUE"),
        {"bc": barcode},
    )).first()
    return int(row[0]) if row else None


async def scan_receive_commit(session: AsyncSession, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    扫码入库通路（保存点探活 + 真动作开关）。

    环境变量：
      - SCAN_REAL_RECEIVE="1" → 真动作入账
      - 其他 → 保存点探活（执行后回滚，不落账）

    统一口径：
      - stocks 唯一键：(item_id, warehouse_id, location_id, batch_code)
      - 入库写正腿台账，保证三账一致
    """
    # 0) 若未给 item_id，尝试从 tokens.item_barcode 解析
    tokens = payload.get("tokens") or {}
    if "item_id" not in payload and isinstance(tokens, dict):
        bc = tokens.get("item_barcode")
        if bc:
            resolved = await _resolve_item_id_by_barcode(session, str(bc))
            if not resolved:
                await log_error("scan_receive_error", "unknown_barcode", {"in": payload})
                raise ValueError(f"unknown_barcode: {bc}")
            payload["item_id"] = resolved

    # 1) 解析输入 + 兜底
    data = ScanReceiveInput(
        device_id=payload.get("device_id", "unknown"),
        operator=payload.get("operator", "unknown"),
        barcode=payload.get("barcode", ""),
        item_id=int(payload["item_id"]),
        qty=int(payload.get("qty", 0)),
        location_id=payload.get("location_id"),
        batch_code=payload.get("batch_code"),
        expire_at=payload.get("expire_at"),
        ctx=payload.get("ctx") or {},
    )

    if data.location_id is None:
        maybe = _parse_location_from_barcode(data.barcode)
        if maybe is not None:
            data.location_id = maybe
    if data.location_id is None:
        stage_loc = os.getenv("SCAN_STAGE_LOCATION_ID")
        data.location_id = int(stage_loc) if stage_loc and stage_loc.isdigit() else 900

    if not data.batch_code:
        data.batch_code = _autogen_batch_code(data.item_id)

    if data.qty <= 0:
        await log_error("scan_receive_error", "invalid_qty", {"in": payload})
        raise ValueError("Receive qty must be positive.")

    # 2) 生成 ref（证据链）
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ref = f"scan:{data.device_id}:{ts}:{data.barcode or 'RECEIVE'}"

    # 3) 真动作 / 探活
    real_mode = os.getenv("SCAN_REAL_RECEIVE") == "1"
    svc = StockService()
    result: Dict[str, Any] = {}

    if real_mode:
        adjust_res = await svc.adjust(
            session=session,
            item_id=data.item_id,
            location_id=data.location_id,
            delta=data.qty,         # 门面使用 delta
            reason="INBOUND",
            ref=ref,
            batch_code=data.batch_code,
            production_date=payload.get("production_date"),
            # expiry 在服务层统一口径计算/或由 DB 层函数计算
        )
        result = {
            "received": int(data.qty),
            "status": "ok",
            "idempotent": bool(adjust_res.get("idempotent", False)) if isinstance(adjust_res, dict) else False,
        }
        # 提交，确保台账/库存落库
        await session.flush()
        await session.commit()
        await log_event("scan_receive_commit", ref, {"in": payload, "out": result, "ctx": data.__dict__})
    else:
        try:
            async with session.begin_nested():  # SAVEPOINT
                _ = await svc.adjust(
                    session=session,
                    item_id=data.item_id,
                    location_id=data.location_id,
                    delta=data.qty,     # 门面使用 delta
                    reason="INBOUND",
                    ref=ref,
                    batch_code=data.batch_code,
                    production_date=payload.get("production_date"),
                )
                raise _ProbeRollback()
        except _ProbeRollback:
            result = {"received": int(data.qty), "status": "probe_ok", "idempotent": False}
            await log_event("scan_receive_probe", ref, {"in": payload, "out": result, "ctx": data.__dict__})

    return {
        "source": "scan_receive_commit",
        "ref": ref,
        "result": result,
        "context": {
            "warehouse_id": data.warehouse_id,
            "location_id": data.location_id,
            "batch_code": data.batch_code,
            "item_id": data.item_id,
        },
    }
