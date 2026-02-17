# app/services/receive_task_create/from_po_selected.py
from __future__ import annotations

from typing import Optional, Sequence, Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.models.receive_task import ReceiveTask, ReceiveTaskLine
from app.schemas.receive_task import ReceiveTaskCreateFromPoSelectedLineIn
from app.services.receive_task_loaders import load_po
from app.services.receive_task_query import get_with_lines

from .validators import normalize_po_selected_lines


def _trim_or_none(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


async def _load_items_map(session: AsyncSession, item_ids: list[int]) -> Dict[int, Item]:
    if not item_ids:
        return {}
    rows = (await session.execute(select(Item).where(Item.id.in_(item_ids)))).scalars().all()
    return {int(it.id): it for it in rows}


def _requires_explicit_expiry(it: Item) -> bool:
    if getattr(it, "has_shelf_life", False) is not True:
        return False
    sv = getattr(it, "shelf_life_value", None)
    su = getattr(it, "shelf_life_unit", None)
    if sv is None:
        return True
    if su is None or not str(su).strip():
        return True
    return False


async def create_for_po_selected(
    session: AsyncSession,
    *,
    po_id: int,
    warehouse_id: Optional[int] = None,
    lines: Sequence[ReceiveTaskCreateFromPoSelectedLineIn],
) -> ReceiveTask:
    """
    从采购单“选择部分行”创建收货任务（本次到货批次）

    ✅ Phase 3 收敛（关键）：
    - 一个 ReceiveTask = 一次到货批次
    - 创建阶段必须携带批次/生产日期等元数据（保质期商品）
    - 禁止静默复用旧 DRAFT（否则会出现“我传入的批次没生效”的假象）
    """
    po = await load_po(session, po_id, for_update=True)
    wh_id = warehouse_id or po.warehouse_id

    # ✅ Phase 3：同一 PO 同一仓库存在 DRAFT 时，明确拒绝创建新批次（不再静默返回旧任务）
    stmt = (
        select(ReceiveTask.id)
        .where(
            ReceiveTask.source_type == "PO",
            ReceiveTask.po_id == po.id,
            ReceiveTask.warehouse_id == wh_id,
            ReceiveTask.status == "DRAFT",
        )
        .order_by(ReceiveTask.id.desc())
        .limit(1)
    )
    existing_id = (await session.execute(stmt)).scalar_one_or_none()
    if existing_id is not None:
        raise ValueError(f"当前采购单已存在待处理的收货任务（DRAFT）#{int(existing_id)}：请先提交入库或取消该任务，再创建新的到货批次任务。")

    meta_by_po_line_id: Dict[int, Dict[str, Any]] = {}
    for ln in lines:
        pid = int(getattr(ln, "po_line_id", 0) or 0)
        if pid <= 0:
            continue
        meta_by_po_line_id[pid] = {
            "batch_code": _trim_or_none(getattr(ln, "batch_code", None)),
            "production_date": getattr(ln, "production_date", None),
            "expiry_date": getattr(ln, "expiry_date", None),
        }

    normalized = normalize_po_selected_lines(
        po_id=po.id,
        po_lines=(po.lines or []),
        lines=lines,
    )

    item_ids = sorted(
        {
            int(getattr(n.po_line_obj, "item_id"))
            for n in normalized
            if getattr(n.po_line_obj, "item_id", None)
        }
    )
    items_map = await _load_items_map(session, item_ids)

    for n in normalized:
        pol = n.po_line_obj
        po_line_id = int(getattr(pol, "id"))
        item_id = int(getattr(pol, "item_id"))
        it = items_map.get(item_id)
        if it is None:
            raise ValueError(f"PO 行 item 不存在，无法创建任务（po_line_id={po_line_id}, item_id={item_id})")

        if getattr(it, "has_shelf_life", False) is True:
            meta = meta_by_po_line_id.get(po_line_id) or {}
            batch_code = _trim_or_none(meta.get("batch_code"))
            prod = meta.get("production_date")
            exp = meta.get("expiry_date")

            if not batch_code:
                raise ValueError(f"保质期商品必须提供批次（po_line_id={po_line_id}, item_id={item_id}）")
            if prod is None:
                raise ValueError(f"保质期商品必须提供生产日期（po_line_id={po_line_id}, item_id={item_id}）")
            if _requires_explicit_expiry(it) and exp is None:
                raise ValueError(f"商品无法推算到期日期，必须提供到期日期（po_line_id={po_line_id}, item_id={item_id}）")

    task = ReceiveTask(
        source_type="PO",
        source_id=po.id,
        po_id=po.id,
        supplier_id=po.supplier_id,
        supplier_name=po.supplier_name or po.supplier,
        warehouse_id=wh_id,
        status="DRAFT",
        remark=f"from PO-{po.id} selected",
    )
    session.add(task)
    await session.flush()

    created_lines: list[ReceiveTaskLine] = []
    for n in normalized:
        pol = n.po_line_obj
        qty_planned_base = n.qty_planned_base

        po_line_id = int(getattr(pol, "id"))
        meta = meta_by_po_line_id.get(po_line_id) or {}

        created_lines.append(
            ReceiveTaskLine(
                task_id=task.id,
                po_line_id=po_line_id,
                item_id=int(getattr(pol, "item_id")),
                item_name=getattr(pol, "item_name", None),
                item_sku=getattr(pol, "item_sku", None),
                category=getattr(pol, "category", None),
                spec_text=getattr(pol, "spec_text", None),
                base_uom=getattr(pol, "base_uom", None),
                purchase_uom=getattr(pol, "purchase_uom", None),
                units_per_case=getattr(pol, "units_per_case", None),
                batch_code=_trim_or_none(meta.get("batch_code")),
                production_date=meta.get("production_date"),
                expiry_date=meta.get("expiry_date"),
                expected_qty=qty_planned_base,
                scanned_qty=0,
                committed_qty=None,
                status="DRAFT",
            )
        )

    if not created_lines:
        raise ValueError(f"采购单 {po.id} 未创建任何任务行，无法创建收货任务")

    for rtl in created_lines:
        session.add(rtl)

    await session.flush()
    return await get_with_lines(session, task.id)
