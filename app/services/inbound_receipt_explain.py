# app/services/inbound_receipt_explain.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.inbound_receipt_explain import (
    InboundReceiptExplainOut,
    InboundReceiptSummaryOut,
    LedgerPreviewOut,
    NormalizedLinePreviewOut,
    ProblemItem,
)

# 标签层伪码（仅用于 lot_code 校验；与时间层无关）
_PSEUDO_LOT_CODE_TOKENS = {"NOEXP", "NONE"}


@dataclass(frozen=True)
class _ItemRules:
    expiry_policy: str  # NONE / REQUIRED
    derivation_allowed: bool
    shelf_life_value: int | None
    shelf_life_unit: str | None
    lot_source_policy: str  # INTERNAL_ONLY / SUPPLIER_ONLY


def _sorted_lines(receipt: object) -> List[object]:
    lines = list(getattr(receipt, "lines", []) or [])
    lines.sort(key=lambda x: (int(getattr(x, "line_no", 0) or 0), int(getattr(x, "id", 0) or 0)))
    return lines


def _validate_header(receipt: object) -> List[ProblemItem]:
    errs: List[ProblemItem] = []

    if getattr(receipt, "occurred_at", None) is None:
        errs.append(ProblemItem(scope="header", field="occurred_at", message="收货日期不能为空"))

    if getattr(receipt, "warehouse_id", None) is None:
        errs.append(ProblemItem(scope="header", field="warehouse_id", message="仓库不能为空"))

    st = getattr(receipt, "source_type", None)
    if st is None or str(st).strip() == "":
        errs.append(ProblemItem(scope="header", field="source_type", message="来源类型不能为空"))

    if getattr(receipt, "source_id", None) is None:
        errs.append(ProblemItem(scope="header", field="source_id", message="来源编号不能为空"))

    status = str(getattr(receipt, "status", "") or "").upper()
    if status not in ("DRAFT", "CONFIRMED"):
        errs.append(ProblemItem(scope="header", field="status", message="收货单状态非法"))

    return errs


def _is_required_policy(v: object) -> bool:
    return str(v or "").strip().upper() == "REQUIRED"


def _normalize_lot_code(v: object) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


async def _load_item_rules_map(session: AsyncSession, item_ids: List[int]) -> Dict[int, _ItemRules]:
    """
    Phase M-2（去耦合版）：
    - 标签层：items.lot_source_policy 决定 lot_code(batch_code) 是否必填
    - 时间层：items.expiry_policy + derivation_allowed + shelf_life_* 决定日期是否必填/是否可推导
    """
    if not item_ids:
        return {}

    rows = (
        (
            await session.execute(
                sa.text(
                    """
                    SELECT
                        id,
                        expiry_policy,
                        derivation_allowed,
                        shelf_life_value,
                        shelf_life_unit,
                        lot_source_policy
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

    out: Dict[int, _ItemRules] = {}
    for r in rows:
        iid = int(r["id"])
        out[iid] = _ItemRules(
            expiry_policy=str(r.get("expiry_policy") or "NONE"),
            derivation_allowed=bool(r.get("derivation_allowed") or False),
            shelf_life_value=(int(r["shelf_life_value"]) if r.get("shelf_life_value") is not None else None),
            shelf_life_unit=(str(r["shelf_life_unit"]) if r.get("shelf_life_unit") is not None else None),
            lot_source_policy=str(r.get("lot_source_policy") or "INTERNAL_ONLY"),
        )
    return out


def _validate_lines(lines: List[object], rules_map: Dict[int, _ItemRules]) -> List[ProblemItem]:
    """
    ✅ Explain 只检查两类错误：
    1) 标签层：lot_source_policy 决定 batch_code(lot_code) 是否必填
    2) 时间层：expiry_policy REQUIRED 采用方案 B（expiry_date 或 production_date 推导）

    ❌ 不检查 lot_id（draft 阶段可不存在）
    ❌ 不做 lot_code × 日期冲突预检（伪命题）
    """
    errs: List[ProblemItem] = []
    if not lines:
        errs.append(ProblemItem(scope="header", field="lines", message="收货明细不能为空"))
        return errs

    for idx, ln in enumerate(lines):
        qty = int(getattr(ln, "qty_received", 0) or 0)
        if qty <= 0:
            errs.append(ProblemItem(scope="line", field="qty_received", message="数量必须大于 0", index=idx))

        if getattr(ln, "po_line_id", None) is None:
            errs.append(ProblemItem(scope="line", field="po_line_id", message="必须关联采购单明细", index=idx))

        item_id = int(getattr(ln, "item_id", 0) or 0)
        rules = rules_map.get(item_id)
        if rules is None:
            errs.append(ProblemItem(scope="line", field="item_id", message="商品规则缺失，无法确认", index=idx))
            continue

        # -------- 标签层（lot_code）--------
        lot_code = _normalize_lot_code(getattr(ln, "batch_code", None))

        if rules.lot_source_policy == "SUPPLIER_ONLY":
            if lot_code is None:
                errs.append(ProblemItem(scope="line", field="batch_code", message="供应商批次码必填", index=idx))
            elif lot_code.upper() in _PSEUDO_LOT_CODE_TOKENS:
                errs.append(ProblemItem(scope="line", field="batch_code", message="批次码禁止伪码（NOEXP/NONE）", index=idx))
        else:
            # INTERNAL_ONLY：可不填；但若填了伪码仍禁止
            if lot_code is not None and lot_code.upper() in _PSEUDO_LOT_CODE_TOKENS:
                errs.append(ProblemItem(scope="line", field="batch_code", message="批次码禁止伪码（NOEXP/NONE）", index=idx))

        # -------- 时间层（方案 B）--------
        pd = getattr(ln, "production_date", None)
        ed = getattr(ln, "expiry_date", None)

        if _is_required_policy(rules.expiry_policy):
            # 必须能得到确定 expiry_date：直接给 expiry_date 或 production_date 推导
            if ed is None:
                if not rules.derivation_allowed:
                    errs.append(ProblemItem(scope="line", field="expiry_date", message="有效期必填（未开启推导）", index=idx))
                else:
                    if pd is None:
                        errs.append(
                            ProblemItem(
                                scope="line",
                                field="production_date",
                                message="未填写有效期：请填写生产日期以便推导",
                                index=idx,
                            )
                        )
                    if rules.shelf_life_value is None or rules.shelf_life_unit is None:
                        errs.append(
                            ProblemItem(
                                scope="line",
                                field="shelf_life",
                                message="未配置保质期参数，无法推导有效期",
                                index=idx,
                            )
                        )
        else:
            # NONE：日期必须为 NULL（保持系统干净）
            if pd is not None:
                errs.append(ProblemItem(scope="line", field="production_date", message="非效期商品生产日期必须为 null", index=idx))
            if ed is not None:
                errs.append(ProblemItem(scope="line", field="expiry_date", message="非效期商品有效期必须为 null", index=idx))

    return errs


def _normalize(lines: List[object]) -> Tuple[List[NormalizedLinePreviewOut], List[Tuple[str, int, int]]]:
    """
    Phase M-2：draft 允许没有 lot_id，因此归一化不使用 lot_id 作为 identity。
    - 每条 receipt_line 产出一条 normalized（line_key=LINE:<line_no>）
    - 不做跨行聚合，避免“无身份锚点的假聚合”
    """
    normalized: List[NormalizedLinePreviewOut] = []
    seeds: List[Tuple[str, int, int]] = []

    for idx, ln in enumerate(lines):
        line_no = int(getattr(ln, "line_no", 0) or 0)
        item_id = int(getattr(ln, "item_id", 0) or 0)
        qty = int(getattr(ln, "qty_received", 0) or 0)

        key = f"LINE:{line_no}" if line_no > 0 else f"IDX:{idx}"

        normalized.append(
            NormalizedLinePreviewOut(
                line_key=key,
                qty_total=qty,
                lot_id=getattr(ln, "lot_id", None),  # draft 可能为 None
                item_id=item_id,
                po_line_id=getattr(ln, "po_line_id", None),
                batch_code=getattr(ln, "batch_code", None),
                production_date=getattr(ln, "production_date", None),
                source_line_indexes=[idx],
            )
        )
        seeds.append((key, item_id, qty))

    normalized.sort(key=lambda x: x.line_key)
    seeds.sort(key=lambda x: x[0])
    return normalized, seeds


async def explain_receipt(*, session: AsyncSession, receipt: object) -> InboundReceiptExplainOut:
    lines = _sorted_lines(receipt)

    header_errs = _validate_header(receipt)

    item_ids = sorted({int(getattr(x, "item_id")) for x in lines}) if lines else []
    rules_map = await _load_item_rules_map(session, item_ids)

    line_errs = _validate_lines(lines, rules_map=rules_map)
    blocking = header_errs + line_errs

    normalized_lines_preview, ledger_seeds = _normalize(lines)

    summary = InboundReceiptSummaryOut(
        id=int(getattr(receipt, "id")),
        status=str(getattr(receipt, "status")),
        occurred_at=getattr(receipt, "occurred_at", None),
        warehouse_id=int(getattr(receipt, "warehouse_id")) if getattr(receipt, "warehouse_id", None) is not None else None,
        source_type=str(getattr(receipt, "source_type", None)) if getattr(receipt, "source_type", None) is not None else None,
        source_id=int(getattr(receipt, "source_id", None)) if getattr(receipt, "source_id", None) is not None else None,
        ref=str(getattr(receipt, "ref", None)) if getattr(receipt, "ref", None) is not None else None,
        trace_id=str(getattr(receipt, "trace_id", None)) if getattr(receipt, "trace_id", None) is not None else None,
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
