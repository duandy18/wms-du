# app/services/purchase_order_receive.py
from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Any, Tuple

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_receipt import InboundReceipt, InboundReceiptLine
from app.models.item import Item
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine
from app.services.purchase_order_queries import get_po_with_lines
from app.services.qty_base import ordered_base as _ordered_base_impl


def _ordered_base(line: Any) -> int:
    return _ordered_base_impl(line)


async def _get_latest_po_draft_receipt(
    session: AsyncSession, *, po_id: int
) -> Optional[InboundReceipt]:
    stmt = (
        select(InboundReceipt)
        .where(InboundReceipt.source_type == "PO")
        .where(InboundReceipt.source_id == int(po_id))
        .where(InboundReceipt.status == "DRAFT")
        .order_by(InboundReceipt.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


async def _get_po_draft_receipt(session: AsyncSession, *, po_id: int) -> Optional[InboundReceipt]:
    return await _get_latest_po_draft_receipt(session, po_id=int(po_id))


async def _create_po_draft_receipt(
    session: AsyncSession,
    *,
    po: PurchaseOrder,
    occurred_at: datetime,
) -> InboundReceipt:
    """
    显式创建 DRAFT receipt（只创建，不复用）。
    注意：DB 有 partial unique（PO + DRAFT），并发下可能冲突。
    """
    ts = int(occurred_at.timestamp() * 1000)
    ref = f"DRFT-PO-{po.id}-{ts}"

    r = InboundReceipt(
        warehouse_id=int(po.warehouse_id),
        supplier_id=getattr(po, "supplier_id", None),
        supplier_name=getattr(po, "supplier_name", None),
        source_type="PO",
        source_id=int(po.id),
        ref=ref,
        trace_id=None,
        status="DRAFT",
        remark="explicit draft (Phase5)",
        occurred_at=occurred_at,
    )
    session.add(r)
    await session.flush()
    return r


async def get_or_create_po_draft_receipt_explicit(
    session: AsyncSession,
    *,
    po: PurchaseOrder,
    occurred_at: datetime,
) -> InboundReceipt:
    """
    显式入口（给 POST draft 用）：
    - 先查现有 DRAFT，有则复用
    - 没有才创建
    - 并发下若触发 partial unique：自动 rollback 后再查一次（幂等）
    """
    draft = await _get_po_draft_receipt(session, po_id=int(po.id))
    if draft is not None:
        return draft

    try:
        return await _create_po_draft_receipt(session, po=po, occurred_at=occurred_at)
    except IntegrityError:
        await session.rollback()
        draft2 = await _get_po_draft_receipt(session, po_id=int(po.id))
        if draft2 is not None:
            return draft2
        raise


async def _next_receipt_line_no(session: AsyncSession, *, receipt_id: int) -> int:
    """
    在 async 环境中禁止访问 receipt.lines（可能触发 lazyload -> MissingGreenlet）。
    用 SQL 直接取 MAX(line_no)+1。
    """
    row = await session.execute(
        text(
            """
            SELECT COALESCE(MAX(line_no), 0) AS mx
              FROM inbound_receipt_lines
             WHERE receipt_id = :rid
            """
        ),
        {"rid": int(receipt_id)},
    )
    mx = int(row.scalar() or 0)
    return mx + 1


def _build_batch_code(*, po_id: int, po_line_no: int, production_date: Optional[date]) -> Optional[str]:
    """
    Phase5+（批次语义封板）：
    - 不再允许 NOEXP 这类“伪批次码”
    - 若 production_date 缺失，则 batch_code 返回 None（由上层根据 has_shelf_life 决定是否允许）
    """
    if production_date is None:
        return None
    return f"BATCH-PO{po_id}-L{po_line_no}-{production_date.isoformat()}"


async def _sum_confirmed_received_base(
    session: AsyncSession, *, po_id: int, po_line_id: int
) -> int:
    sql = text(
        """
        SELECT COALESCE(SUM(rl.qty_received), 0)::int AS qty
          FROM inbound_receipt_lines rl
          JOIN inbound_receipts r
            ON r.id = rl.receipt_id
         WHERE r.source_type='PO'
           AND r.source_id=:po_id
           AND r.status='CONFIRMED'
           AND rl.po_line_id=:po_line_id
        """
    )
    return int(
        (await session.execute(sql, {"po_id": int(po_id), "po_line_id": int(po_line_id)})).scalar()
        or 0
    )


async def _sum_draft_received_base(
    session: AsyncSession, *, receipt_id: int, po_line_id: int
) -> int:
    sql = text(
        """
        SELECT COALESCE(SUM(qty_received), 0)::int AS qty
          FROM inbound_receipt_lines
         WHERE receipt_id=:rid
           AND po_line_id=:po_line_id
        """
    )
    return int(
        (
            await session.execute(sql, {"rid": int(receipt_id), "po_line_id": int(po_line_id)})
        ).scalar()
        or 0
    )


async def _get_item_shelf_life_flag(session: AsyncSession, *, item_id: int) -> bool:
    """
    写入口守护所需：判断该商品是否效期管理（has_shelf_life）。
    """
    row = await session.execute(select(Item.has_shelf_life).where(Item.id == int(item_id)))
    val = row.scalar_one_or_none()
    return bool(val)


def _normalize_barcode(barcode: Optional[str]) -> Optional[str]:
    if barcode is None:
        return None
    s = str(barcode).strip()
    return s or None


def _enforce_batch_semantics(
    *,
    has_shelf_life: bool,
    production_date: Optional[date],
    expiry_date: Optional[date],
    batch_code: Optional[str],
) -> Tuple[Optional[date], Optional[date], Optional[str]]:
    """
    ✅ Phase5+ 批次写入口封板（语义层）：

    - has_shelf_life=False：
        - 强制 batch_code=NULL
        - 强制 production_date/expiry_date=NULL
      目的：彻底杜绝“非效期商品被迫写入伪批次/伪日期”。

    - has_shelf_life=True：
        - batch_code 必须存在
        - production_date / expiry_date 必须存在
      目的：让效期商品批次事实完整可追溯。
    """
    if not has_shelf_life:
        return None, None, None

    # has_shelf_life=True
    if batch_code is None or not str(batch_code).strip():
        raise ValueError("效期商品必须提供/生成 batch_code（禁止空值/伪批次）")
    if production_date is None:
        raise ValueError("效期商品必须提供 production_date")
    if expiry_date is None:
        raise ValueError("效期商品必须提供 expiry_date")
    return production_date, expiry_date, str(batch_code).strip()


async def _ensure_batch_consistent(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    batch_code: str,
    production_date: Optional[date],
    expiry_date: Optional[date],
) -> None:
    """
    ✅ canonical（batches）一致性硬守护：

    - 若 canonical 不存在：创建 batches 记录（以本次写入为准）
    - 若 canonical 已存在：production/expiry 必须一致，否则 409

    说明：
    - batches 的唯一键是 (warehouse_id, item_id, batch_code)
    - canonical 的日期来源必须稳定，否则 downstream 会出现“日期来源漂移”
    """
    # 1) 查询 canonical
    row = await session.execute(
        text(
            """
            SELECT production_date, expiry_date
              FROM batches
             WHERE warehouse_id = :wid
               AND item_id = :item_id
               AND batch_code = :batch_code
             LIMIT 1
            """
        ),
        {"wid": int(warehouse_id), "item_id": int(item_id), "batch_code": str(batch_code)},
    )
    existing = row.first()

    # 2) 不存在 -> 创建 canonical
    if existing is None:
        await session.execute(
            text(
                """
                INSERT INTO batches (warehouse_id, item_id, batch_code, production_date, expiry_date)
                VALUES (:wid, :item_id, :batch_code, :pd, :ed)
                """
            ),
            {
                "wid": int(warehouse_id),
                "item_id": int(item_id),
                "batch_code": str(batch_code),
                "pd": production_date,
                "ed": expiry_date,
            },
        )
        return

    # 3) 已存在 -> 必须一致，否则 409
    existing_pd = existing[0]
    existing_ed = existing[1]

    # 注意：date / None 的比较 Python 直接可比
    if existing_pd != production_date or existing_ed != expiry_date:
        raise HTTPException(
            status_code=409,
            detail=(
                "批次 canonical 不一致：batches 与本次写入的 snapshot 日期冲突。"
                f" (warehouse_id={int(warehouse_id)}, item_id={int(item_id)}, batch_code={str(batch_code)}, "
                f"canonical.production_date={existing_pd}, canonical.expiry_date={existing_ed}, "
                f"snapshot.production_date={production_date}, snapshot.expiry_date={expiry_date})"
            ),
        )


async def receive_po_line(
    session: AsyncSession,
    *,
    po_id: int,
    line_id: Optional[int] = None,
    line_no: Optional[int] = None,
    qty: int,
    occurred_at: Optional[datetime] = None,
    production_date: Optional[date] = None,
    expiry_date: Optional[date] = None,
    barcode: Optional[str] = None,
) -> PurchaseOrder:
    """
    Phase5：对某一行执行“收货录入”（行级）。
    - ✅ 只写 Receipt(DRAFT) 事实（InboundReceipt / InboundReceiptLine）
    - ❌ 不写 stock_ledger / stocks / snapshot（库存动作只能由 Receipt(CONFIRMED) 触发）
    - qty 为最小单位（base）

    关键收敛：不再依赖 purchase_order_lines.qty_received/status/category 等字段。
    余量校验以 Receipt 事实为准：remaining = ordered_base - confirmed_received_base - draft_received_base
    """
    if qty <= 0:
        raise ValueError("收货数量 qty 必须 > 0")
    if line_id is None and line_no is None:
        raise ValueError("receive_po_line 需要提供 line_id 或 line_no 之一")

    po = await get_po_with_lines(session, po_id, for_update=True)
    if po is None:
        raise ValueError(f"PurchaseOrder not found: id={po_id}")
    if not po.lines:
        raise ValueError(f"采购单 {po_id} 没有任何行，无法执行行级收货")

    target: Optional[PurchaseOrderLine] = None
    if line_id is not None:
        for line in po.lines:
            if line.id == line_id:
                target = line
                break
    elif line_no is not None:
        for line in po.lines:
            if line.line_no == line_no:
                target = line
                break

    if target is None:
        raise ValueError(
            f"在采购单 {po_id} 中未找到匹配的行 (line_id={line_id}, line_no={line_no})"
        )

    # 1) 必须已有 DRAFT Receipt（显式创建）
    draft = await _get_po_draft_receipt(session, po_id=int(po.id))
    if draft is None:
        raise ValueError(f"请先开始收货：未找到 PO 的 DRAFT 收货单 (po_id={po_id})")

    ordered_base = int(_ordered_base(target) or 0)
    if ordered_base <= 0:
        raise ValueError(
            f"行订购数量非法（base 口径）：ordered_base={ordered_base} (line_id={target.id})"
        )

    confirmed_received_base = await _sum_confirmed_received_base(
        session, po_id=int(po.id), po_line_id=int(target.id)
    )
    draft_received_base = await _sum_draft_received_base(
        session, receipt_id=int(draft.id), po_line_id=int(target.id)
    )

    remaining_base = max(0, ordered_base - confirmed_received_base - draft_received_base)
    if qty > remaining_base:
        raise ValueError(
            f"行收货数量超出剩余数量（base 口径）：ordered_base={ordered_base}, "
            f"confirmed_received_base={confirmed_received_base}, draft_received_base={draft_received_base}, "
            f"remaining_base={remaining_base}, try_receive={qty}"
        )

    # 2) 生成 receipt_line_no（receipt 内递增）
    next_line_no = await _next_receipt_line_no(session, receipt_id=int(draft.id))

    # 3) 批次语义写入口守护（has_shelf_life）
    item_id_val = int(getattr(target, "item_id"))
    has_shelf_life = await _get_item_shelf_life_flag(session, item_id=item_id_val)

    units_per_case = int(getattr(target, "units_per_case", 1) or 1)
    po_line_no_val = int(getattr(target, "line_no", 0) or 0)
    raw_batch_code = _build_batch_code(
        po_id=int(po.id),
        po_line_no=po_line_no_val,
        production_date=production_date,
    )

    enforced_production_date, enforced_expiry_date, enforced_batch_code = _enforce_batch_semantics(
        has_shelf_life=has_shelf_life,
        production_date=production_date,
        expiry_date=expiry_date,
        batch_code=raw_batch_code,
    )

    # 4) canonical 一致性硬守护（仅对效期商品）
    # - 非效期：enforced_* 全为 None，不触发 batches
    # - 效期：必须写入/对齐 batches，冲突则 409
    if has_shelf_life:
        await _ensure_batch_consistent(
            session,
            warehouse_id=int(getattr(draft, "warehouse_id")),
            item_id=item_id_val,
            batch_code=str(enforced_batch_code),
            production_date=enforced_production_date,
            expiry_date=enforced_expiry_date,
        )

    # 5) 写入 ReceiptLine（snapshot）
    rl = InboundReceiptLine(
        receipt_id=int(draft.id),
        line_no=int(next_line_no),
        po_line_id=int(getattr(target, "id")),
        item_id=item_id_val,
        item_name=getattr(target, "item_name", None),
        item_sku=getattr(target, "item_sku", None),
        category=None,  # ✅ PO 行不再承载 category
        spec_text=getattr(target, "spec_text", None),
        base_uom=getattr(target, "base_uom", None),
        purchase_uom=getattr(target, "purchase_uom", None),
        barcode=_normalize_barcode(barcode),
        batch_code=enforced_batch_code,
        production_date=enforced_production_date,
        expiry_date=enforced_expiry_date,
        qty_received=int(qty),
        units_per_case=int(units_per_case),
        qty_units=int(qty),  # 继续沿用 base=units 的既有口径
        unit_cost=None,
        line_amount=None,
        remark=None,
    )
    session.add(rl)
    await session.flush()

    return po
