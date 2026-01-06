# app/services/receive_task_supplement_service.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.receive_task import ReceiveTask
from app.schemas.receive_task_supplement import ReceiveSupplementLineOut, ReceiveSupplementSummaryOut
from app.services.receive_task_loaders import load_item_policy_map


def normalize_mode(mode: Optional[str]) -> str:
    m = (mode or "hard").strip().lower()
    if m not in {"hard", "soft"}:
        raise ValueError("mode must be hard or soft")
    return m


def compute_missing_fields(*, mode: str, has_shelf_life: bool, line, item_info: dict) -> list[str]:
    """
    返回缺失字段列表（字段名用后端字段：batch_code/production_date/expiry_date）

    规则与 commit / 旧实现保持一致：
    - soft：建议补录（不一定阻断 commit）
    - hard：阻断项（与 commit 对齐）
    """
    missing: list[str] = []

    if mode == "soft":
        # 只要已收，缺批次就建议补（无论是否有保质期）
        if not line.batch_code or not str(line.batch_code).strip():
            missing.append("batch_code")

        # 有保质期：建议补齐生产/到期（即便可推算也建议补包装到期日）
        if has_shelf_life:
            if line.production_date is None:
                missing.append("production_date")
            if line.expiry_date is None:
                missing.append("expiry_date")

        return missing

    # hard：阻断项（与 commit 对齐）
    if has_shelf_life:
        if not line.batch_code or not str(line.batch_code).strip():
            missing.append("batch_code")

        if line.production_date is None:
            missing.append("production_date")

        if line.expiry_date is None:
            sv = item_info.get("shelf_life_value")
            su = item_info.get("shelf_life_unit")
            if sv is None or su is None or not str(su).strip():
                missing.append("expiry_date")

    return missing


async def list_receive_supplements(
    session: AsyncSession,
    *,
    warehouse_id: Optional[int] = None,
    source_type: Optional[str] = None,
    po_id: Optional[int] = None,
    limit: int = 200,
    mode: Optional[str] = None,
) -> list[ReceiveSupplementLineOut]:
    """
    补录清单（给前端“补录中心/补录抽屉”使用）。
    """
    mode_norm = normalize_mode(mode)

    stmt = (
        select(ReceiveTask)
        .options(selectinload(ReceiveTask.lines))
        .order_by(ReceiveTask.id.desc())
        .limit(max(int(limit or 1), 1))
    )

    if warehouse_id is not None:
        stmt = stmt.where(ReceiveTask.warehouse_id == warehouse_id)

    if source_type and source_type.strip():
        stmt = stmt.where(ReceiveTask.source_type == source_type.strip().upper())

    if po_id is not None:
        stmt = stmt.where(ReceiveTask.po_id == po_id)

    res = await session.execute(stmt)
    tasks = list(res.scalars())

    item_ids: list[int] = sorted(
        {
            int(ln.item_id)
            for t in tasks
            for ln in (t.lines or [])
            if ln.item_id is not None
        }
    )
    policy_map = await load_item_policy_map(session, item_ids) if item_ids else {}

    out: list[ReceiveSupplementLineOut] = []

    for t in tasks:
        for ln in (t.lines or []):
            scanned = int(ln.scanned_qty or 0)
            if scanned <= 0:
                continue

            info = policy_map.get(int(ln.item_id)) or {}
            has_sl = bool(info.get("has_shelf_life") or False)

            missing = compute_missing_fields(
                mode=mode_norm,
                has_shelf_life=has_sl,
                line=ln,
                item_info=info,
            )
            if not missing:
                continue

            out.append(
                ReceiveSupplementLineOut(
                    task_id=t.id,
                    po_id=t.po_id,
                    source_type=t.source_type,
                    source_id=int(t.source_id) if t.source_id is not None else None,
                    warehouse_id=t.warehouse_id,
                    item_id=int(ln.item_id),
                    item_name=ln.item_name,
                    scanned_qty=scanned,
                    batch_code=ln.batch_code,
                    production_date=ln.production_date,
                    expiry_date=ln.expiry_date,
                    missing_fields=missing,
                )
            )

    return out


async def summarize_receive_supplements(
    session: AsyncSession,
    *,
    warehouse_id: Optional[int] = None,
    source_type: Optional[str] = None,
    po_id: Optional[int] = None,
    limit: int = 200,
    mode: Optional[str] = None,
) -> ReceiveSupplementSummaryOut:
    """
    汇总：统计缺失字段分布，用于 UI 顶部提示。
    """
    mode_norm = normalize_mode(mode)
    rows = await list_receive_supplements(
        session,
        warehouse_id=warehouse_id,
        source_type=source_type,
        po_id=po_id,
        limit=limit,
        mode=mode_norm,
    )

    by_field: dict[str, int] = {}
    for r in rows:
        for f in r.missing_fields or []:
            by_field[f] = by_field.get(f, 0) + 1

    return ReceiveSupplementSummaryOut(
        mode=mode_norm,
        total_rows=len(rows),
        by_field=by_field,
    )
