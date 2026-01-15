# app/services/receive_task_create/validators.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence

from app.schemas.receive_task import OrderReturnLineIn, ReceiveTaskCreateFromPoSelectedLineIn

from .common import ordered_base_from_line, received_base


@dataclass(frozen=True)
class NormalizedPoSelectedLine:
    """
    归一化后的 PO 选择行（base 口径）。
    - qty_planned_base：本次计划收货量（最小单位 base）
    - remaining_base：剩余应收（最小单位 base）
    """
    po_line_id: int
    qty_planned_base: int
    po_line_obj: object
    ordered_base: int
    received_base_qty: int
    remaining_base: int


@dataclass(frozen=True)
class NormalizedOrderReturnLine:
    """
    归一化后的 ORDER 退货行（base 口径）。
    - qty_base：本次退货量（最小单位 base）
    - cap_base：本次最大可退（最小单位 base）
    """
    item_id: int
    item_name: str | None
    batch_code: str | None
    qty_base: int
    cap_base: int


def normalize_po_selected_lines(
    *,
    po_id: int,
    po_lines: Iterable[object],
    lines: Sequence[ReceiveTaskCreateFromPoSelectedLineIn],
) -> List[NormalizedPoSelectedLine]:
    """
    校验 + 去重 + belongs_to_po + remaining_base（base）校验 + 输入范围校验。

    ✅ 硬规则（Phase 2）：
    - 所有数量比较均为 base 口径（最小单位）
    """
    if not lines:
        raise ValueError("lines 不能为空")

    po_lines_map: Dict[int, object] = {}
    for ln in po_lines or []:
        po_lines_map[int(getattr(ln, "id"))] = ln

    seen: set[int] = set()
    out: List[NormalizedPoSelectedLine] = []

    for req in lines:
        plid = int(req.po_line_id)

        if plid in seen:
            raise ValueError(f"lines 中存在重复 po_line_id={plid}")
        seen.add(plid)

        if plid not in po_lines_map:
            raise ValueError(f"po_line_id={plid} 不属于采购单 {po_id}")

        qty_planned_base = int(req.qty_planned)  # base
        if qty_planned_base <= 0:
            raise ValueError(f"po_line_id={plid} 的 qty_planned 必须 > 0")

        pol = po_lines_map[plid]
        ordered_base = ordered_base_from_line(pol)  # base
        received_base_qty = received_base(getattr(pol, "qty_received", None))  # base
        remaining_base = max(ordered_base - received_base_qty, 0)  # base

        if remaining_base <= 0:
            raise ValueError(f"po_line_id={plid} 已无剩余应收，不能选择")

        # ✅ base 口径比较（硬规则）
        if qty_planned_base > remaining_base:
            raise ValueError(
                f"po_line_id={plid} 本次计划量超出剩余应收（base 口径）："
                f"ordered_base={ordered_base} received_base={received_base_qty} remaining_base={remaining_base} "
                f"qty_planned={qty_planned_base}"
            )

        out.append(
            NormalizedPoSelectedLine(
                po_line_id=plid,
                qty_planned_base=qty_planned_base,
                po_line_obj=pol,
                ordered_base=ordered_base,
                received_base_qty=received_base_qty,
                remaining_base=remaining_base,
            )
        )

    if not out:
        raise ValueError(f"采购单 {po_id} 未选择任何有效行，无法创建收货任务")

    return out


def normalize_order_return_lines_base(
    *,
    order_id: int,
    lines: Sequence[OrderReturnLineIn],
    order_qty_map: Dict[int, int],
    shipped_qty_map: Dict[int, int],
    returned_qty_map: Dict[int, int],
) -> List[NormalizedOrderReturnLine]:
    """
    ORDER 退货创建：校验 + 归一化（base 口径）。

    ✅ 硬规则（Phase 2）：
    - orig / shipped / returned / qty 均为 base（最小单位）
    - 所有数量比较均为 base 口径
    """
    if not lines:
        raise ValueError("退货行不能为空")

    out: List[NormalizedOrderReturnLine] = []
    for rc in lines:
        orig_base = int(order_qty_map.get(rc.item_id, 0))
        shipped_base = int(shipped_qty_map.get(rc.item_id, 0))
        returned_base = int(returned_qty_map.get(rc.item_id, 0))
        cap_base = max(min(orig_base, shipped_base) - returned_base, 0)  # base

        if orig_base <= 0:
            raise ValueError(
                f"订单 {order_id} 中不存在或未记录 item_id={rc.item_id} 的原始数量，无法为该商品创建退货任务"
            )
        if shipped_base <= 0:
            raise ValueError(
                f"订单 {order_id} 的商品 item_id={rc.item_id} 尚未发货（shipped=0），不能创建退货任务"
            )

        qty_base = int(rc.qty)  # base
        if qty_base <= 0:
            # ✅ 明确：qty<=0 的行不进入创建（但不算错误）
            continue

        # ✅ base 口径比较（硬规则）
        if qty_base > cap_base:
            raise ValueError(
                f"订单 {order_id} 的商品 item_id={rc.item_id} 退货数量超出可退上限（base 口径）："
                f"原始数量={orig_base}，已发货={shipped_base}，已退={returned_base}，本次请求={qty_base}，剩余可退={cap_base}"
            )

        out.append(
            NormalizedOrderReturnLine(
                item_id=int(rc.item_id),
                item_name=getattr(rc, "item_name", None),
                batch_code=getattr(rc, "batch_code", None),
                qty_base=qty_base,
                cap_base=cap_base,
            )
        )

    if not out:
        raise ValueError("退货行数量必须大于 0")

    return out


def validate_order_return_lines_base(
    *,
    order_id: int,
    lines: Sequence[OrderReturnLineIn],
    order_qty_map: Dict[int, int],
    shipped_qty_map: Dict[int, int],
    returned_qty_map: Dict[int, int],
) -> None:
    """
    仅校验（兼容保留）。
    """
    _ = normalize_order_return_lines_base(
        order_id=order_id,
        lines=lines,
        order_qty_map=order_qty_map,
        shipped_qty_map=shipped_qty_map,
        returned_qty_map=returned_qty_map,
    )
