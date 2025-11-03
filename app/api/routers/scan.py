from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.routers.scan_utils import fill_from_barcode, make_scan_ref

router = APIRouter()


class ScanRequest(BaseModel):
    mode: Literal["pick", "receive", "putaway", "count"]
    item_id: Optional[int] = None
    location_id: Optional[int] = Field(default=None, description="目标库位（receive/putaway/count）")
    qty: Optional[int] = None
    task_id: Optional[int] = None
    from_location_id: Optional[int] = None
    tokens: Optional[Dict[str, Any]] = None
    ctx: Optional[Dict[str, Any]] = None  # {"device_id": "...", "operator": "..."}
    probe: Optional[bool] = False

    @model_validator(mode="before")
    @classmethod
    def _fill_missing_from_barcode(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return fill_from_barcode(data)
        return data


async def _insert_event(session: AsyncSession, *, source: str, message: str, occurred_at: datetime) -> int:
    row = await session.execute(
        text(
            "INSERT INTO event_log(source, message, occurred_at) "
            "VALUES (:s, :m, :t) RETURNING id"
        ),
        {"s": source, "m": message, "t": occurred_at},
    )
    return int(row.scalar())  # type: ignore


async def _ensure_stock_slot_id(
    session: AsyncSession, *, item_id: int, location_id: int
) -> int:
    """
    返回给定 (item_id, location_id) 的一个有效 stocks.id。
    若不存在，则以 qty=0 创建一个“槽位”后返回其 id。
    """
    # 1) 尝试已有 stocks.id
    row = await session.execute(
        text(
            "SELECT id FROM stocks "
            "WHERE item_id=:item AND location_id=:loc "
            "ORDER BY id LIMIT 1"
        ),
        {"item": item_id, "loc": location_id},
    )
    sid = row.scalar()
    if sid:
        return int(sid)

    # 2) 不存在则创建：需要 warehouse_id
    wh_row = await session.execute(
        text("SELECT warehouse_id FROM locations WHERE id=:loc"),
        {"loc": location_id},
    )
    wh_id = wh_row.scalar()
    if not wh_id:
        # 极端情况：位置不存在
        raise HTTPException(status_code=400, detail=f"location {location_id} not found")

    # 3) 创建 0 数量槽位（batch_code 允许为 NULL；若不允许，请按项目规则给默认批次）
    await session.execute(
        text(
            "INSERT INTO stocks(item_id, warehouse_id, location_id, batch_code, qty) "
            "VALUES (:item, :wh, :loc, NULL, 0) "
            "ON CONFLICT DO NOTHING"
        ),
        {"item": item_id, "wh": int(wh_id), "loc": location_id},
    )
    # 4) 再取一次 id
    row2 = await session.execute(
        text(
            "SELECT id FROM stocks "
            "WHERE item_id=:item AND location_id=:loc "
            "ORDER BY id LIMIT 1"
        ),
        {"item": item_id, "loc": location_id},
    )
    sid2 = row2.scalar()
    if not sid2:
        # 理论不应发生
        raise HTTPException(status_code=500, detail="failed to create stock slot")
    return int(sid2)


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

    if req.mode == "count":
        if req.item_id is None or req.location_id is None or req.qty is None:
            raise HTTPException(status_code=400, detail="count requires ITEM, LOC, QTY(actual)")
        async with session.begin():
            result = await svc.reconcile_inventory(
                session=session,
                item_id=int(req.item_id),
                location_id=int(req.location_id),
                counted_qty=int(req.qty),
                apply=True,
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
            "result": result,
        }

    if req.mode == "putaway":
        if req.item_id is None or req.location_id is None or req.qty is None or req.from_location_id is None:
            raise HTTPException(status_code=400, detail="putaway requires ITEM, LOC, QTY and from_location_id")

        src = int(req.from_location_id)
        dst = int(req.location_id)
        qty = int(req.qty)
        item = int(req.item_id)

        async with session.begin():
            # 双腿：源位扣、目标位加；统一 reason/ref
            await svc.adjust(
                session=session,
                item_id=item,
                location_id=src,
                delta=-qty,
                reason="PUTAWAY",
                ref=scan_ref,
            )
            await svc.adjust(
                session=session,
                item_id=item,
                location_id=dst,
                delta=+qty,
                reason="PUTAWAY",
                ref=scan_ref,
            )

            # ===== 兜底：确保能按 ref 命中两腿，且满足 stock_id NOT NULL =====

            # A) 统一 reason -> PUTAWAY
            await session.execute(
                text("UPDATE stock_ledger SET reason='PUTAWAY' WHERE ref=:ref"),
                {"ref": scan_ref},
            )

            # B) stock_id/location_id 尽量用 stocks 反填
            await session.execute(
                text(
                    "UPDATE stock_ledger AS l "
                    "SET location_id = s.location_id "
                    "FROM stocks AS s "
                    "WHERE l.ref = :ref AND l.stock_id = s.id "
                    "  AND (l.location_id IS NULL OR l.location_id <> s.location_id)"
                ),
                {"ref": scan_ref},
            )

            # C) 若仍没有任何账页，直接补记两腿（先确保有 stock_id 槽位）
            cnt = (
                await session.execute(
                    text("SELECT COUNT(*) FROM stock_ledger WHERE ref=:ref"),
                    {"ref": scan_ref},
                )
            ).scalar()
            if int(cnt or 0) == 0:
                src_sid = await _ensure_stock_slot_id(session, item_id=item, location_id=src)
                dst_sid = await _ensure_stock_slot_id(session, item_id=item, location_id=dst)
                await session.execute(
                    text(
                        "INSERT INTO stock_ledger (stock_id, reason, ref, ref_line, delta, item_id, location_id, occurred_at) "
                        "VALUES (:sid1, 'PUTAWAY', :ref, 1, :neg, :item, :src, :ts), "
                        "       (:sid2, 'PUTAWAY', :ref, 2, :pos, :item, :dst, :ts)"
                    ),
                    {
                        "sid1": src_sid,
                        "sid2": dst_sid,
                        "ref": scan_ref,
                        "neg": -qty,
                        "pos": qty,
                        "item": item,
                        "src": src,
                        "dst": dst,
                        "ts": occurred_at,
                    },
                )
            else:
                # D) 若已有账页但缺 location_id，用符号兜底
                await session.execute(
                    text(
                        "UPDATE stock_ledger "
                        "SET location_id = :src "
                        "WHERE ref=:ref AND location_id IS NULL AND delta < 0"
                    ),
                    {"ref": scan_ref, "src": src},
                )
                await session.execute(
                    text(
                        "UPDATE stock_ledger "
                        "SET location_id = :dst "
                        "WHERE ref=:ref AND location_id IS NULL AND delta > 0"
                    ),
                    {"ref": scan_ref, "dst": dst},
                )

            ev_id = await _insert_event(session, source="scan_putaway_commit", message=scan_ref, occurred_at=occurred_at)

        return {
            "scan_ref": scan_ref,
            "ref": scan_ref,
            "source": "scan_putaway_commit",
            "occurred_at": occurred_at.isoformat(),
            "committed": True,
            "event_id": ev_id,
            "result": {"moved": qty, "from_location_id": src, "to_location_id": dst},
        }

    raise HTTPException(status_code=400, detail="unsupported mode")
