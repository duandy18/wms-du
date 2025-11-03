# app/api/routers/scan.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Literal

import json
import re
import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session

router = APIRouter()

# ---------- helpers ----------

def _format_ref(ts: datetime, device_id: Optional[str], location_id: Optional[int]) -> str:
    did = (device_id or "unknown").lower()
    loc = f"{location_id}" if location_id is not None else "unknown"
    # 测试断言期望以 "scan:" 开头，统一小写
    return f"scan:{did}:{ts.isoformat()}:loc:{loc}".lower()


async def _insert_event_raw(
    session: AsyncSession,
    source: str,
    message: str | Dict[str, Any],
    occurred_at: datetime,
) -> int:
    msg_text = message if isinstance(message, str) else json.dumps(message, ensure_ascii=False)
    row = await session.execute(
        sa.text(
            """
            INSERT INTO event_log(source, message, occurred_at)
            VALUES (:source, :message, :occurred_at)
            RETURNING id
            """
        ),
        {"source": source, "message": msg_text, "occurred_at": occurred_at},
    )
    return int(row.scalar_one())


async def _commit_and_get_event_id(
    session: AsyncSession, source: str, message: str | Dict[str, Any], occurred_at: datetime
) -> int:
    ev_id = await _insert_event_raw(session, source, message, occurred_at)
    await session.commit()
    return ev_id


# ---------- request schema (Pydantic) ----------

ScanMode = Literal["pick", "receive", "putaway", "count"]


class ScanCtxModel(BaseModel):
    device_id: Optional[str] = None
    operator: Optional[str] = None


class ScanTokensModel(BaseModel):
    barcode: Optional[str] = None


_BARCODE_INT = re.compile(r"\b(\w+):([-\w\.]+)\b", re.I)

class ScanRequest(BaseModel):
    mode: ScanMode
    tokens: ScanTokensModel = Field(default_factory=ScanTokensModel)
    ctx: ScanCtxModel = Field(default_factory=ScanCtxModel)

    # 直给场景（不依赖条码）
    task_line_id: Optional[int] = None
    task_id: Optional[int] = None
    item_id: Optional[int] = None
    qty: Optional[int] = None
    location_id: Optional[int] = None
    from_location_id: Optional[int] = None

    # 行为
    probe: bool = False

    @field_validator("task_id", "item_id", "qty", "location_id", mode="before")
    @classmethod
    def fill_from_barcode(cls, v, info):
        """
        若 body 未直给，尝试从 tokens.barcode 解析
        """
        # info.data 是已解析字段字典；拿到 tokens
        tokens = info.data.get("tokens") or {}
        barcode = tokens.get("barcode") or ""
        if v is not None or not isinstance(barcode, str) or not barcode:
            return v

        kv = {m.group(1).upper(): m.group(2) for m in _BARCODE_INT.finditer(barcode)}
        key = info.field_name
        mapping = {
            "task_id": "TASK",
            "item_id": "ITEM",
            "qty": "QTY",
            "location_id": "LOC",
        }
        tag = mapping.get(key)
        if tag and tag in kv:
            raw = kv[tag]
            try:
                return int(raw)
            except ValueError:
                return v
        return v


def _fallback_loc_id_from_barcode(payload: Dict[str, Any]) -> Optional[int]:
    tokens = payload.get("tokens") or {}
    barcode = tokens.get("barcode") or ""
    if isinstance(barcode, str):
        m = re.search(r"\bloc:(\d+)\b", barcode, re.I)
        if m:
            return int(m.group(1))
    return None


# ---------- endpoint ----------

@router.post("/scan")
async def scan_gateway(
    req: ScanRequest, session: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """
    统一 /scan 网关（pick / receive / putaway / count）：
    - 使用 Pydantic 校验必填字段
    - 写事件：pick（probe/commit）message 写纯文本 scan_ref；其它模式写 JSON
    - putaway 采用“原子事务”两腿 adjust，reason 统一为 PUTAWAY
    """
    # 兜底 location
    loc_id = req.location_id if req.location_id is not None else _fallback_loc_id_from_barcode(req.model_dump())
    occurred_at = datetime.now(timezone.utc)
    scan_ref = _format_ref(occurred_at, req.ctx.device_id, loc_id)

    meta_input: Dict[str, Any] = {
        "mode": req.mode,
        "task_id": req.task_id,
        "item_id": req.item_id,
        "qty": req.qty,
        "location_id": loc_id,
    }

    # ---------- pick ----------
    if req.mode == "pick":
        if req.probe:
            # probe：写文本 ref
            source = "scan_pick_probe"
            ev_id = await _commit_and_get_event_id(session, source, scan_ref, occurred_at)
            return {
                "scan_ref": scan_ref,
                "ref": scan_ref,
                "source": source,
                "occurred_at": occurred_at.isoformat(),
                "committed": False,
                "event_id": ev_id,
                "result": {"hint": "pick probe"},
            }
        else:
            # commit：延迟导入 pick 服务；测试里会注入假的 PickService
            try:
                from app.services.pick_service import PickService  # type: ignore
            except Exception as e:  # pragma: no cover
                raise HTTPException(status_code=500, detail=f"pick service missing: {e}")

            if req.item_id is None or loc_id is None or req.qty is None:
                raise HTTPException(status_code=400, detail="pick requires TASK/ITEM/LOC/QTY")

            svc = PickService()
            result = await svc.record_pick(
                session=session,
                task_line_id=int(req.task_line_id) if req.task_line_id is not None else (req.task_id or 0),
                from_location_id=loc_id,
                item_id=req.item_id,
                qty=int(req.qty),
                scan_ref=scan_ref,
                operator=req.ctx.operator,
            )
            source = "scan_pick_commit"
            # commit：也写文本 ref（与测试断言一致）
            ev_id = await _commit_and_get_event_id(session, source, scan_ref, occurred_at)
            return {
                "scan_ref": scan_ref,
                "ref": scan_ref,
                "source": source,
                "occurred_at": occurred_at.isoformat(),
                "committed": True,
                "event_id": ev_id,
                "result": result,
            }

    # ---------- receive / putaway / count ----------
    # probe：写文本 ref
    if req.probe:
        source = f"scan_{req.mode}_probe"
        ev_id = await _commit_and_get_event_id(session, source, scan_ref, occurred_at)
        return {
            "scan_ref": scan_ref,
            "ref": scan_ref,
            "source": source,
            "occurred_at": occurred_at.isoformat(),
            "committed": False,
            "event_id": ev_id,
            "result": {"hint": f"{req.mode} probe"},
        }

    # 真动作
    from app.services.stock_service import StockService
    svc = StockService()

    if req.mode == "receive":
        if req.item_id is None or loc_id is None or req.qty is None:
            raise HTTPException(status_code=400, detail="receive requires ITEM, LOC, QTY")
        # 单腿正向
        result = await svc.adjust(
            session=session,
            item_id=req.item_id,
            location_id=loc_id,
            delta=+int(req.qty),
            reason="INBOUND",
            ref=scan_ref,
        )
        source = "scan_receive_commit"
        msg: str | Dict[str, Any] = {**meta_input, "ref": scan_ref}

    elif req.mode == "putaway":
        if req.item_id is None or loc_id is None or req.qty is None or req.from_location_id is None:
            raise HTTPException(status_code=400, detail="putaway requires ITEM, LOC, QTY and from_location_id")

        qty = int(req.qty)
        # 两腿原子事务（避免“只出不入”）
        async with session.begin():
            # 源位负出
            await svc.adjust(
                session=session,
                item_id=req.item_id,
                location_id=int(req.from_location_id),
                delta=-qty,
                reason="PUTAWAY",
                ref=scan_ref,
            )
            # 目标正入
            await svc.adjust(
                session=session,
                item_id=req.item_id,
                location_id=loc_id,
                delta=+qty,
                reason="PUTAWAY",
                ref=scan_ref,
            )
            # 兜底：将本 ref 的 reason 统一回填为 PUTAWAY
            await session.execute(
                sa.text("UPDATE stock_ledger SET reason='PUTAWAY' WHERE ref=:ref"),
                {"ref": scan_ref},
            )

        source = "scan_putaway_commit"
        msg = {**meta_input, "ref": scan_ref}
        result = {
            "moved": qty,
            "from_location_id": int(req.from_location_id),
            "to_location_id": loc_id,
        }

        ev_id = await _commit_and_get_event_id(session, source, msg, occurred_at)
        return {
            "scan_ref": scan_ref,
            "ref": scan_ref,
            "source": source,
            "occurred_at": occurred_at.isoformat(),
            "committed": True,
            "event_id": ev_id,
            "result": result,
        }

    else:  # req.mode == "count"
        if req.item_id is None or loc_id is None or req.qty is None:
            raise HTTPException(status_code=400, detail="count requires ITEM, LOC, QTY(actual)")
        result = await svc.reconcile_inventory(
            session=session,
            item_id=req.item_id,
            location_id=loc_id,
            counted_qty=int(req.qty),  # 注意：这里是 counted_qty
            apply=True,
            ref=scan_ref,
        )
        source = "scan_count_commit"
        msg = {**meta_input, "ref": scan_ref}

    ev_id = await _commit_and_get_event_id(session, source, msg, occurred_at)
    return {
        "scan_ref": scan_ref,
        "ref": scan_ref,
        "source": source,
        "occurred_at": occurred_at.isoformat(),
        "committed": True,
        "event_id": ev_id,
        "result": result,
    }
