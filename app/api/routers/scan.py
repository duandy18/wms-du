from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.api.deps import get_session
from app.api.routers.scan_utils import fill_from_barcode, make_scan_ref

# 说明：
# - 本路由保持高内聚：网关解析/校验 + 统一生成 scan_ref + 事件审计（可选） + 调用服务
# - 条码解析与回填已抽离到 scan_utils.py（parse_barcode/fill_from_barcode/make_scan_ref）

router = APIRouter()


class ScanRequest(BaseModel):
    mode: Literal["pick", "receive", "putaway", "count"]
    # 可选直传字段（若缺失会从 tokens.barcode 自动回填）
    item_id: Optional[int] = None
    location_id: Optional[int] = Field(default=None, description="目标库位（receive/putaway/count）")
    qty: Optional[int] = None
    task_id: Optional[int] = None

    # putaway 专用：源库位
    from_location_id: Optional[int] = None

    # 上下文
    tokens: Optional[Dict[str, Any]] = None
    ctx: Optional[Dict[str, Any]] = None  # {"device_id": "RF01", "operator": "qa"}
    probe: Optional[bool] = False

    @model_validator(mode="before")
    @classmethod
    def _fill_missing_from_barcode(cls, data: Any) -> Any:
        # 先做一次从条码回填
        if isinstance(data, dict):
            return fill_from_barcode(data)
        return data


async def _insert_event(session: AsyncSession, *, source: str, message: str, occurred_at: datetime) -> int:
    """
    写入 event_log，并返回 id（message 用 TEXT；不依赖 ref 列）。
    """
    row = await session.execute(
        text(
            "INSERT INTO event_log(source, message, occurred_at) "
            "VALUES (:s, :m, :t) RETURNING id"
        ),
        {"s": source, "m": message, "t": occurred_at},
    )
    return int(row.scalar())  # type: ignore


@router.post("/scan")
async def scan_gateway(req: ScanRequest, session: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
    """
    高并发/高弹性入口：
    - 统一条码解析与回填（scan_utils.fill_from_barcode）
    - 统一生成 scan_ref（scan_utils.make_scan_ref）
    - probe → 只记审计；commit → 走服务层
    """
    # 解析上下文
    device_id = (req.ctx or {}).get("device_id") if isinstance(req.ctx, dict) else None
    operator = (req.ctx or {}).get("operator") if isinstance(req.ctx, dict) else None

    occurred_at = datetime.now(timezone.utc)
    scan_ref = make_scan_ref(device_id, occurred_at, req.location_id)

    # ------- pick -------
    if req.mode == "pick":
        if req.probe:
            # 只写审计（message=scan_ref 纯文本，兼容既有断言）
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

        # commit：延迟导入，避免循环依赖
        try:
            from app.services.pick_service import PickService  # type: ignore
        except Exception as e:
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

    # ------- receive / putaway / count -------
    # probe 路径统一：只审计，不改库存
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

    # commit 路径
    try:
        from app.services.stock_service import StockService  # type: ignore
    except Exception as e:
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
            # StockService.reconcile_inventory 的形参命名为 counted_qty
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
        # 关键修复：自动从 barcode 回填 item_id/location_id/qty
        if req.item_id is None or req.location_id is None or req.qty is None or req.from_location_id is None:
            raise HTTPException(status_code=400, detail="putaway requires ITEM, LOC, QTY and from_location_id")

        src = int(req.from_location_id)
        dst = int(req.location_id)
        qty = int(req.qty)
        item = int(req.item_id)

        async with session.begin():
            # 双腿账页（-qty 源位 / +qty 目标位），同一 reason/ref
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

    # 兜底（理论上不会命中）
    raise HTTPException(status_code=400, detail="unsupported mode")
