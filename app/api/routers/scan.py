# app/api/routers/scan.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session

router = APIRouter()


# --------- 简单的扫码上下文解析 ---------
class ScanContext:
    def __init__(
        self,
        *,
        mode: str,
        task_id: Optional[int],
        location_id: Optional[int],
        item_id: Optional[int],
        qty: Optional[int],
        device_id: str,
        operator: Optional[str],
    ):
        self.mode = mode
        self.task_id = task_id
        self.location_id = location_id
        self.item_id = item_id
        self.qty = qty
        self.device_id = device_id
        self.operator = operator


def extract_scan_context(payload: Dict[str, Any]) -> ScanContext:
    tokens = payload.get("tokens") or {}
    barcode = tokens.get("barcode") or ""
    # 支持 "LOC:1 ITEM:3001 QTY:2" 这种键值对
    kv: Dict[str, str] = {}
    for part in str(barcode).replace(",", " ").split():
        if ":" in part:
            k, v = part.split(":", 1)
            kv[k.strip().upper()] = v.strip()

    def _to_int(s: Optional[str]) -> Optional[int]:
        try:
            return int(str(s)) if s is not None else None
        except Exception:
            return None

    mode = str(payload.get("mode") or "").strip().lower()
    return ScanContext(
        mode=mode,
        task_id=_to_int(kv.get("TASK")),
        location_id=_to_int(kv.get("LOC")),
        item_id=_to_int(kv.get("ITEM")),
        qty=_to_int(kv.get("QTY")),
        device_id=str((payload.get("ctx") or {}).get("device_id") or "RF"),
        operator=(payload.get("ctx") or {}).get("operator"),
    )


# ---------- 事件记录（简化实现） ----------
async def _insert_event_raw(
    session: AsyncSession,
    source: str,
    ref: str,
    meta_base: Dict[str, Any],
    occurred_at: datetime,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO event_log(source, ref, message, occurred_at)
            VALUES (:src, :ref, :msg, :ts)
        """
        ),
        {
            "src": source,
            "ref": ref,
            # 这里 message 只做最小化信息存储；完整信息通常放 meta/jsonb
            "msg": meta_base.get("input", {}),
            "ts": occurred_at,
        },
    )


async def _commit_and_get_event_id(session: AsyncSession, ref: str, source: str) -> int:
    await session.commit()
    row = await session.execute(
        text(
            """
            SELECT id FROM event_log
             WHERE ref=:ref AND source=:src
             ORDER BY id DESC LIMIT 1
        """
        ),
        {"ref": ref, "src": source},
    )
    v = row.scalar_one_or_none()
    return int(v) if v is not None else 0


def _format_ref(ts: datetime, device_id: str, loc_id: Optional[int]) -> str:
    # 统一的扫描参考号：SCAN-<MODE>:scan:<DEVICE>:<ISO8601>:LOC:<id>
    loc = loc_id if loc_id is not None else 0
    return f"SCAN:scan:{device_id}:{ts.isoformat()}:LOC:{loc}"


def _fallback_loc_id_from_barcode(payload: Dict[str, Any]) -> Optional[int]:
    # 兜底从 tokens.barcode 拆 LOC:xx
    tokens = payload.get("tokens") or {}
    barcode = tokens.get("barcode") or ""
    for part in str(barcode).replace(",", " ").split():
        if part.upper().startswith("LOC:"):
            try:
                return int(part.split(":", 1)[1])
            except Exception:
                return None
    return None


@router.post("/scan")
async def scan_gateway(
    payload: Dict[str, Any], session: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    sc = extract_scan_context(payload)
    if sc.mode not in {"pick", "receive", "putaway", "count"}:
        raise HTTPException(status_code=400, detail="invalid mode")

    occurred_at = datetime.now(timezone.utc)
    probe = bool(payload.get("probe", False))
    loc_id = sc.location_id if sc.location_id is not None else _fallback_loc_id_from_barcode(payload)
    scan_ref = _format_ref(occurred_at, sc.device_id, loc_id)

    meta_base: Dict[str, Any] = {
        "occurred_at": occurred_at.isoformat(),
        "ctx": {"device_id": sc.device_id, "operator": sc.operator},
        "input": {
            "mode": sc.mode,
            "task_id": sc.task_id,
            "item_id": sc.item_id,
            "qty": sc.qty,
            "location_id": loc_id,
        },
        "ref": scan_ref,
    }

    # pick probe
    if sc.mode == "pick" and probe:
        source = "scan_pick_probe"
        await _insert_event_raw(session, source, scan_ref, meta_base, occurred_at)
        ev_id = await _commit_and_get_event_id(session, scan_ref, source)
        return {
            "scan_ref": scan_ref,
            "ref": scan_ref,
            "source": source,
            "occurred_at": occurred_at.isoformat(),
            "committed": False,
            "event_id": ev_id,
            "result": {"hint": "pick probe"},
        }

    # === receive/putaway/count：probe 或 commit ===
    if sc.mode in {"receive", "putaway", "count"}:
        if probe:
            source = f"scan_{sc.mode}_probe"
            await _insert_event_raw(session, source, scan_ref, meta_base, occurred_at)
            ev_id = await _commit_and_get_event_id(session, scan_ref, source)
            return {
                "scan_ref": scan_ref,
                "ref": scan_ref,
                "source": source,
                "occurred_at": occurred_at.isoformat(),
                "committed": False,
                "event_id": ev_id,
                "result": {"hint": f"{sc.mode} probe"},
            }

        # -------- commit 真动作（串行执行） --------
        from app.services.stock_service import StockService

        svc = StockService()

        if sc.mode == "receive":
            if sc.item_id is None or loc_id is None or sc.qty is None:
                raise HTTPException(status_code=400, detail="receive requires ITEM, LOC, QTY")
            result = await svc.adjust(
                session=session,
                item_id=sc.item_id,
                location_id=loc_id,
                delta=+int(sc.qty),
                reason="INBOUND",
                ref=scan_ref,
            )
            source = "scan_receive_commit"

        elif sc.mode == "putaway":
            from_loc = payload.get("from_location_id")
            if from_loc is None:
                raise HTTPException(status_code=400, detail="putaway requires from_location_id")
            if sc.item_id is None or loc_id is None or sc.qty is None:
                raise HTTPException(status_code=400, detail="putaway requires ITEM, LOC, QTY")

            # 注意：transfer 当前签名**不接受** reason 参数
            result = await svc.transfer(
                session=session,
                item_id=sc.item_id,
                from_location_id=int(from_loc),
                to_location_id=loc_id,
                qty=int(sc.qty),
                ref=scan_ref,
            )
            source = "scan_putaway_commit"

        else:  # sc.mode == "count"
            if sc.item_id is None or loc_id is None or sc.qty is None:
                raise HTTPException(status_code=400, detail="count requires ITEM, LOC, QTY(actual)")

            # StockService.reconcile_inventory 的包装更偏好 counted_qty 参数名（内部已做向后兼容）
            result = await svc.reconcile_inventory(
                session=session,
                item_id=sc.item_id,
                location_id=loc_id,
                counted_qty=int(sc.qty),
                apply=True,
                ref=scan_ref,
            )
            source = "scan_count_commit"

        # 写事件 + 返回
        await _insert_event_raw(session, source, scan_ref, meta_base, occurred_at)
        ev_id = await _commit_and_get_event_id(session, scan_ref, source)
        return {
            "scan_ref": scan_ref,
            "ref": scan_ref,
            "source": source,
            "occurred_at": occurred_at.isoformat(),
            "committed": True,
            "event_id": ev_id,
            "result": result,
        }

    # 不应到达
    raise HTTPException(status_code=400, detail="unsupported mode")
