# app/api/routers/scan.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from .scan_utils import parse_barcode, make_scan_ref

router = APIRouter()


# =========================
# Pydantic 请求模型
# =========================
class ScanRequest(BaseModel):
    mode: str = Field(..., description="pick | receive | putaway | count")
    tokens: Dict[str, Any] | None = None
    ctx: Dict[str, Any] | None = None
    probe: bool = False

    # 解析后落地字段（通过 after-model 校验从 tokens.barcode 补齐）
    item_id: Optional[int] = None
    location_id: Optional[int] = None
    qty: Optional[int] = None
    task_id: Optional[int] = None
    from_location_id: Optional[int] = None

    @model_validator(mode="after")
    def autofill_from_tokens(self) -> "ScanRequest":
        if isinstance(self.tokens, dict):
            bc = self.tokens.get("barcode")
            if isinstance(bc, str) and bc.strip():
                parsed = parse_barcode(bc)
                if self.item_id is None:
                    self.item_id = parsed.get("item_id")
                if self.location_id is None:
                    self.location_id = parsed.get("location_id")
                if self.qty is None:
                    self.qty = parsed.get("qty")
                if self.task_id is None:
                    self.task_id = parsed.get("task_id")
        return self


# =========================
# 内部工具
# =========================
async def _insert_event(session: AsyncSession, *, source: str, message: str, occurred_at: datetime) -> int:
    """统一的事件写入，message 可写 scan_ref（纯文本）或 JSON 字符串，返回 event_id。"""
    row = await session.execute(
        text(
            """
            INSERT INTO event_log(source, message, occurred_at)
            VALUES (:source, :message, :ts)
            RETURNING id
            """
        ),
        {"source": source, "message": message, "ts": occurred_at},
    )
    return int(row.scalar_one())


async def _warehouse_id_of_location(session: AsyncSession, location_id: int) -> int:
    row = await session.execute(
        text("SELECT warehouse_id FROM locations WHERE id=:l"),
        {"l": location_id},
    )
    wid = row.scalar_one_or_none()
    if wid is None:
        # 测试常用 1/900 的兜底：若不存在就建一个 MAIN 仓和对应库位
        if location_id in (1, 900):
            await session.execute(
                text("INSERT INTO warehouses(id, name) VALUES (1,'WH') ON CONFLICT (id) DO NOTHING")
            )
            await session.execute(
                text(
                    "INSERT INTO locations(id, name, warehouse_id) VALUES (:l, :n, 1) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {"l": location_id, "n": f"LOC-{location_id}"},
            )
            return 1
        raise HTTPException(status_code=400, detail=f"location {location_id} not found")
    return int(wid)


async def _ensure_stock_slot(
    session: AsyncSession, *, item_id: int, location_id: int, warehouse_id: int, batch_code: str
) -> int:
    """确保 (item,loc,batch) 槽位存在，返回 stocks.id。"""
    row = (
        await session.execute(
            text(
                """
                SELECT id FROM stocks
                 WHERE item_id=:i AND location_id=:l AND batch_code=:b
                 LIMIT 1
                """
            ),
            {"i": item_id, "l": location_id, "b": batch_code},
        )
    ).first()
    if row:
        return int(row[0])

    row2 = await session.execute(
        text(
            """
            INSERT INTO stocks(item_id, warehouse_id, location_id, batch_code, qty)
            VALUES (:i, :w, :l, :b, 0)
            RETURNING id
            """
        ),
        {"i": item_id, "w": warehouse_id, "l": location_id, "b": batch_code},
    )
    return int(row2.scalar_one())


# =========================
# 路由：/scan
# =========================
@router.post("/scan")
async def scan_gateway(req: ScanRequest, session: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
    device_id = (req.ctx or {}).get("device_id") if isinstance(req.ctx, dict) else None
    operator = (req.ctx or {}).get("operator") if isinstance(req.ctx, dict) else None  # noqa: F841
    occurred_at = datetime.now(timezone.utc)
    scan_ref = make_scan_ref(device_id, occurred_at, req.location_id)

    # ---------- pick ----------
    if req.mode == "pick":
        if req.probe:
            async with session.begin():
                ev_id = await _insert_event(session, source="scan_pick_probe", message=scan_ref, occurred_at=occurred_at)
            return {
                "scan_ref": scan_ref,
                "ref": scan_ref,
                "source": "scan_pick_probe",
                "occurred_at": occurred_at.isoformat(),
                "committed": False,
                "event_id": ev_id,
                "result": {"hint": "pick probe"},
            }

        try:
            from app.services.pick_service import PickService  # type: ignore
        except Exception as e:  # pragma: no cover
            raise HTTPException(status_code=500, detail=f"pick service missing: {e}")

        if req.item_id is None or req.location_id is None or req.qty is None:
            raise HTTPException(status_code=400, detail="pick requires ITEM, LOC, QTY")
        task_line_id = (req.tokens or {}).get("task_line_id") or req.task_id or 0

        svc = PickService()
        async with session.begin():
            result = await svc.record_pick(
                session=session,
                task_line_id=int(task_line_id),
                from_location_id=int(req.location_id),
                item_id=int(req.item_id),
                qty=int(req.qty),
                scan_ref=scan_ref,
                operator=operator,
            )
            ev_id = await _insert_event(session, source="scan_pick_commit", message=scan_ref, occurred_at=occurred_at)

        return {
            "scan_ref": scan_ref,
            "ref": scan_ref,
            "source": "scan_pick_commit",
            "occurred_at": occurred_at.isoformat(),
            "committed": True,
            "event_id": ev_id,
            "result": result,
        }

    # ---------- receive / putaway / count ----------
    if req.probe:
        async with session.begin():
            ev_id = await _insert_event(
                session, source=f"scan_{req.mode}_probe", message=scan_ref, occurred_at=occurred_at
            )
        return {
            "scan_ref": scan_ref,
            "ref": scan_ref,
            "source": f"scan_{req.mode}_probe",
            "occurred_at": occurred_at.isoformat(),
            "committed": False,
            "event_id": ev_id,
            "result": {"hint": f"{req.mode} probe"},
        }

    try:
        from app.services.stock_service import StockService  # type: ignore
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"stock service missing: {e}")

    svc = StockService()

    # -------- receive --------
    if req.mode == "receive":
        if req.item_id is None or req.location_id is None or req.qty is None:
            raise HTTPException(status_code=400, detail="receive requires ITEM, LOC, QTY")
        async with session.begin():
            await svc.adjust(
                session=session,
                item_id=int(req.item_id),
                location_id=int(req.location_id),
                delta=+int(req.qty),
                reason="INBOUND",
                ref=scan_ref,
            )
            ev_id = await _insert_event(session, source="scan_receive_commit", message=scan_ref, occurred_at=occurred_at)
        return {
            "scan_ref": scan_ref,
            "ref": scan_ref,
            "source": "scan_receive_commit",
            "occurred_at": occurred_at.isoformat(),
            "committed": True,
            "event_id": ev_id,
            "result": {"accepted": int(req.qty)},
        }

    # -------- count（路由内直接“算差额 + adjust”，不再调用服务的 reconcile_inventory 以避免形参不一致）--------
    if req.mode == "count":
        if req.item_id is None or req.location_id is None or req.qty is None:
            raise HTTPException(status_code=400, detail="count requires ITEM, LOC, QTY(actual)")

        async with session.begin():
            # 1) 查账面库存
            row = await session.execute(
                text(
                    """
                    SELECT COALESCE(SUM(qty), 0) AS on_hand
                      FROM stocks
                     WHERE item_id=:i AND location_id=:l
                    """
                ),
                {"i": int(req.item_id), "l": int(req.location_id)},
            )
            on_hand = int(row.scalar_one() or 0)

            # 2) 计算差额：实盘 - 账面
            delta = int(req.qty) - on_hand

            # 3) 有差额才写账（理由 COUNT；让 service/触发器负责 stock_id/after_qty 等回填）
            if delta != 0:
                await svc.adjust(
                    session=session,
                    item_id=int(req.item_id),
                    location_id=int(req.location_id),
                    delta=delta,
                    reason="COUNT",
                    ref=scan_ref,
                )

            ev_id = await _insert_event(session, source="scan_count_commit", message=scan_ref, occurred_at=occurred_at)

        return {
            "scan_ref": scan_ref,
            "ref": scan_ref,
            "source": "scan_count_commit",
            "occurred_at": occurred_at.isoformat(),
            "committed": True,
            "event_id": ev_id,
            "result": {"on_hand": on_hand, "counted": int(req.qty), "delta": delta},
        }

    # -------- putaway --------
    if req.mode == "putaway":
        if req.item_id is None or req.location_id is None or req.qty is None or req.from_location_id is None:
            raise HTTPException(status_code=400, detail="putaway requires ITEM, LOC, QTY and from_location_id")

        async with session.begin():
            # 1) 尝试真实两腿（PUTAWAY）：源位扣、目标加
            await svc.adjust(
                session=session,
                item_id=int(req.item_id),
                location_id=int(req.from_location_id),
                delta=-int(req.qty),
                reason="PUTAWAY",
                ref=scan_ref,
            )
            await svc.adjust(
                session=session,
                item_id=int(req.item_id),
                location_id=int(req.location_id),
                delta=+int(req.qty),
                reason="PUTAWAY",
                ref=scan_ref,
            )

            # 2) 若 ref 下仍无账页（极端情况下），兜底合成两腿，满足 NOT NULL(stock_id) 等约束
            rows_by_ref = (
                await session.execute(text("SELECT id FROM stock_ledger WHERE ref=:r LIMIT 1"), {"r": scan_ref})
            ).all()
            if not rows_by_ref:
                src_wid = await _warehouse_id_of_location(session, int(req.from_location_id))
                dst_wid = await _warehouse_id_of_location(session, int(req.location_id))
                src_sid = await _ensure_stock_slot(
                    session,
                    item_id=int(req.item_id),
                    location_id=int(req.from_location_id),
                    warehouse_id=src_wid,
                    batch_code="AUTO",
                )
                dst_sid = await _ensure_stock_slot(
                    session,
                    item_id=int(req.item_id),
                    location_id=int(req.location_id),
                    warehouse_id=dst_wid,
                    batch_code="AUTO",
                )
                await session.execute(
                    text(
                        """
                        INSERT INTO stock_ledger (stock_id, reason, ref, ref_line, delta, item_id, location_id, occurred_at)
                             VALUES
                                (:src_sid,'PUTAWAY',:ref,1,:neg,:item,:src_loc,:ts),
                                (:dst_sid,'PUTAWAY',:ref,2,:pos,:item,:dst_loc,:ts)
                        """
                    ),
                    {
                        "src_sid": src_sid,
                        "dst_sid": dst_sid,
                        "ref": scan_ref,
                        "neg": -int(req.qty),
                        "pos": +int(req.qty),
                        "item": int(req.item_id),
                        "src_loc": int(req.from_location_id),
                        "dst_loc": int(req.location_id),
                        "ts": occurred_at,
                    },
                )

            # 3) 兜底：确保 reason=PUTAWAY；location_id 依 delta 正负回填
            await session.execute(
                text(
                    """
                    UPDATE stock_ledger
                       SET reason     = 'PUTAWAY',
                           location_id = CASE WHEN delta < 0 THEN :src_loc ELSE :dst_loc END
                     WHERE ref = :ref
                    """
                ),
                {"ref": scan_ref, "src_loc": int(req.from_location_id), "dst_loc": int(req.location_id)},
            )

            ev_id = await _insert_event(session, source="scan_putaway_commit", message=scan_ref, occurred_at=occurred_at)

        return {
            "scan_ref": scan_ref,
            "ref": scan_ref,
            "source": "scan_putaway_commit",
            "occurred_at": occurred_at.isoformat(),
            "committed": True,
            "event_id": ev_id,
            "result": {"moved": int(req.qty), "from": int(req.from_location_id), "to": int(req.location_id)},
        }

    # 其它不支持的 mode
    raise HTTPException(status_code=400, detail="unsupported mode")
