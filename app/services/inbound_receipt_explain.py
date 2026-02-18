# app/services/inbound_receipt_explain.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.inbound_receipt_explain import (
    InboundReceiptExplainOut,
    InboundReceiptSummaryOut,
    LedgerPreviewOut,
    NormalizedLinePreviewOut,
    ProblemItem,
)


@dataclass(frozen=True)
class _LineKeyFields:
    po_line_id: Optional[int]
    item_id: int
    batch_code: str
    production_date: Optional[date]


def _line_key(f: _LineKeyFields) -> str:
    """
    Phase5（采购收货）归一化键（当前按生产日期口径）：
    po_line_id + item_id + batch_code + production_date
    """
    pol = f.po_line_id if f.po_line_id is not None else "NA"
    pd = f.production_date.isoformat() if f.production_date is not None else "NA"
    return f"POL:{pol}|ITEM:{f.item_id}|B:{f.batch_code}|PD:{pd}"


def _sorted_lines(receipt: object) -> List[object]:
    lines = list(getattr(receipt, "lines", []) or [])
    # 稳定输出：按 (line_no, id) 排序
    lines.sort(key=lambda x: (int(getattr(x, "line_no", 0)), int(getattr(x, "id", 0))))
    return lines


def _validate_header(receipt: object) -> List[ProblemItem]:
    errs: List[ProblemItem] = []

    # 这些在 DB 上是 NOT NULL，但 explain 作为“防脏数据/历史数据兜底”仍保留校验
    if getattr(receipt, "occurred_at", None) is None:
        errs.append(ProblemItem(scope="header", field="occurred_at", message="收货日期不能为空"))

    if getattr(receipt, "warehouse_id", None) is None:
        errs.append(ProblemItem(scope="header", field="warehouse_id", message="仓库不能为空"))

    st = getattr(receipt, "source_type", None)
    if st is None or str(st).strip() == "":
        errs.append(ProblemItem(scope="header", field="source_type", message="来源类型不能为空"))

    # source_id 在模型允许为空（Optional[int]），这里作为 Phase5 采购收货建议硬要求（来源要可追溯）
    if getattr(receipt, "source_id", None) is None:
        errs.append(ProblemItem(scope="header", field="source_id", message="来源编号不能为空"))

    # Phase5：只允许 DRAFT/CONFIRMED（模型里还有 CANCELLED）
    status = str(getattr(receipt, "status", "")).upper()
    if status not in ("DRAFT", "CONFIRMED"):
        errs.append(ProblemItem(scope="header", field="status", message="收货单状态非法"))

    return errs


async def _load_item_has_shelf_life_map(session: AsyncSession, item_ids: List[int]) -> Dict[int, bool]:
    """
    批量加载 items.has_shelf_life，用于校验策略分流：
    - has_shelf_life=true：production_date 必填
    - has_shelf_life=false：允许 production_date 为空（典型 NOEXP）
    """
    if not item_ids:
        return {}
    rows = (
        (
            await session.execute(
                sa.text(
                    """
                    SELECT id, has_shelf_life
                      FROM items
                     WHERE id = ANY(:ids)
                    """
                ),
                {"ids": [int(x) for x in item_ids]},
            )
        )
        .mappings()
        .all()
    )
    m: Dict[int, bool] = {}
    for r in rows:
        iid = int(r["id"])
        m[iid] = bool(r.get("has_shelf_life") or False)
    return m


def _validate_lines(lines: List[object], has_shelf_life_map: Dict[int, bool]) -> List[ProblemItem]:
    errs: List[ProblemItem] = []
    if len(lines) == 0:
        errs.append(ProblemItem(scope="header", field="lines", message="收货明细不能为空"))
        return errs

    for idx, ln in enumerate(lines):
        qty = int(getattr(ln, "qty_received", 0) or 0)
        if qty <= 0:
            errs.append(ProblemItem(scope="line", field="qty_received", message="数量必须大于 0", index=idx))

        # Phase5 合同锚点硬要求（当前字段名：po_line_id）
        if getattr(ln, "po_line_id", None) is None:
            errs.append(ProblemItem(scope="line", field="po_line_id", message="必须关联采购单明细", index=idx))

        # batch_code 在 DB 上 NOT NULL，但仍做兜底
        bc = str(getattr(ln, "batch_code", "") or "").strip()
        if bc == "":
            errs.append(ProblemItem(scope="line", field="batch_code", message="批次必填", index=idx))

        item_id = int(getattr(ln, "item_id"))
        has_sl = bool(has_shelf_life_map.get(item_id, False))

        # ✅ 日期策略分流（关键修复）：
        # - 有效期商品：生产日期必填
        # - 无有效期商品：允许 production_date/expiry_date 为空（NOEXP）
        if has_sl and getattr(ln, "production_date", None) is None:
            errs.append(ProblemItem(scope="line", field="production_date", message="生产日期必填", index=idx))

    return errs


def _normalize(lines: List[object]) -> Tuple[List[NormalizedLinePreviewOut], List[Tuple[str, int, int]]]:
    """
    返回：
    - normalized line preview
    - ledger preview seeds: (line_key, item_id, qty_total)
    """
    groups: Dict[str, Dict[str, object]] = {}

    for idx, ln in enumerate(lines):
        f = _LineKeyFields(
            po_line_id=getattr(ln, "po_line_id", None),
            item_id=int(getattr(ln, "item_id")),
            batch_code=str(getattr(ln, "batch_code")),
            production_date=getattr(ln, "production_date", None),
        )
        key = _line_key(f)

        if key not in groups:
            groups[key] = {
                "po_line_id": f.po_line_id,
                "item_id": f.item_id,
                "batch_code": f.batch_code,
                "production_date": f.production_date,
                "qty": 0,
                "indexes": [],
            }

        groups[key]["qty"] = int(groups[key]["qty"]) + int(getattr(ln, "qty_received", 0) or 0)
        groups[key]["indexes"].append(idx)

    normalized: List[NormalizedLinePreviewOut] = []
    ledger_seeds: List[Tuple[str, int, int]] = []

    for key, g in groups.items():
        qty_total = int(g["qty"])
        item_id = int(g["item_id"])
        normalized.append(
            NormalizedLinePreviewOut(
                line_key=key,
                qty_total=qty_total,
                item_id=item_id,
                po_line_id=g["po_line_id"],
                batch_code=str(g["batch_code"]),
                production_date=g["production_date"],
                source_line_indexes=list(g["indexes"]),
            )
        )
        ledger_seeds.append((key, item_id, qty_total))

    normalized.sort(key=lambda x: x.line_key)
    ledger_seeds.sort(key=lambda x: x[0])
    return normalized, ledger_seeds


async def explain_receipt(*, session: AsyncSession, receipt: object) -> InboundReceiptExplainOut:
    """
    Preflight explain：
    - 不写库
    - 输出 confirmable + blocking_errors + 归一化预览 + ledger 预览
    """
    lines = _sorted_lines(receipt)

    header_errs = _validate_header(receipt)

    item_ids = sorted({int(getattr(x, "item_id")) for x in lines}) if lines else []
    has_sl_map = await _load_item_has_shelf_life_map(session, item_ids)

    line_errs = _validate_lines(lines, has_shelf_life_map=has_sl_map)
    blocking = header_errs + line_errs

    normalized_lines_preview, ledger_seeds = _normalize(lines)

    summary = InboundReceiptSummaryOut(
        id=int(getattr(receipt, "id")),
        status=str(getattr(receipt, "status")),
        occurred_at=getattr(receipt, "occurred_at", None),
        warehouse_id=int(getattr(receipt, "warehouse_id"))
        if getattr(receipt, "warehouse_id", None) is not None
        else None,
        source_type=str(getattr(receipt, "source_type", None))
        if getattr(receipt, "source_type", None) is not None
        else None,
        source_id=int(getattr(receipt, "source_id", None))
        if getattr(receipt, "source_id", None) is not None
        else None,
        ref=str(getattr(receipt, "ref", None)) if getattr(receipt, "ref", None) is not None else None,
        trace_id=str(getattr(receipt, "trace_id", None))
        if getattr(receipt, "trace_id", None) is not None
        else None,
    )

    warehouse_id = int(getattr(receipt, "warehouse_id"))

    ledger_preview: List[LedgerPreviewOut] = [
        LedgerPreviewOut(
            action="INBOUND_RECEIPT_CONFIRM",
            warehouse_id=warehouse_id,
            item_id=item_id,
            qty_delta=qty_total,
            source_line_key=key,
        )
        for (key, item_id, qty_total) in ledger_seeds
    ]

    confirmable = len(blocking) == 0

    return InboundReceiptExplainOut(
        receipt_summary=summary,
        confirmable=confirmable,
        blocking_errors=blocking,
        normalized_lines_preview=normalized_lines_preview,
        ledger_preview=ledger_preview,
    )
