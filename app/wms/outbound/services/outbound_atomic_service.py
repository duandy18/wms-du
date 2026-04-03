from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.outbound.contracts.outbound_atomic import (
    OutboundAtomicCreateIn,
    OutboundAtomicCreateOut,
    OutboundAtomicResultRow,
)


@dataclass(slots=True)
class ResolvedOutboundLine:
    """
    原子出库内部解析结果。
    """

    item_id: int
    barcode: str | None
    qty: int


async def _resolve_lines(
    session: AsyncSession,
    payload: OutboundAtomicCreateIn,
) -> list[ResolvedOutboundLine]:
    """
    解析出库行。

    当前阶段只做骨架，不写完整实现。
    后续这里应负责：
    - item_id / barcode -> 商品解析
    - 行级基础校验
    """
    _ = session

    resolved: list[ResolvedOutboundLine] = []
    for line in payload.lines:
        if line.item_id is None:
            raise NotImplementedError("barcode-only resolution is not implemented yet")

        resolved.append(
            ResolvedOutboundLine(
                item_id=int(line.item_id),
                barcode=line.barcode,
                qty=int(line.qty),
            )
        )
    return resolved


async def _apply_outbound_lines(
    session: AsyncSession,
    *,
    warehouse_id: int,
    lines: Sequence[ResolvedOutboundLine],
    source_type: str,
    source_biz_type: str | None,
    source_ref: str | None,
    remark: str | None,
    trace_id: str,
) -> list[OutboundAtomicResultRow]:
    """
    执行原子出库。

    当前阶段只做骨架，不写完整实现。
    后续这里应负责：
    - lot 分配
    - stocks_lot 扣减
    - stock_ledger 写入
    - 返回分配摘要
    """
    _ = (
        session,
        warehouse_id,
        lines,
        source_type,
        source_biz_type,
        source_ref,
        remark,
        trace_id,
    )

    raise NotImplementedError("outbound atomic execution is not implemented yet")


async def create_outbound_atomic(
    session: AsyncSession,
    payload: OutboundAtomicCreateIn,
) -> OutboundAtomicCreateOut:
    """
    WMS 原子出库入口。

    目标：
    - 不依赖订单存在
    - 只依赖 WMS 核心事实：仓库、地址、商品、数量、来源
    - 上游业务单据只通过 source_type/source_biz_type/source_ref 附带进入

    当前阶段：
    - 已定入口合同
    - 已定内部执行分层
    - 未完成底层扣减实现
    """
    trace_id = f"OUT-ATOMIC-{uuid4().hex[:20]}"

    resolved_lines = await _resolve_lines(session, payload)

    rows = await _apply_outbound_lines(
        session,
        warehouse_id=int(payload.warehouse_id),
        lines=resolved_lines,
        source_type=payload.source_type,
        source_biz_type=payload.source_biz_type,
        source_ref=payload.source_ref,
        remark=payload.remark,
        trace_id=trace_id,
    )

    return OutboundAtomicCreateOut(
        ok=True,
        warehouse_id=int(payload.warehouse_id),
        source_type=payload.source_type,
        source_biz_type=payload.source_biz_type,
        source_ref=payload.source_ref,
        trace_id=trace_id,
        rows=rows,
    )


__all__ = [
    "ResolvedOutboundLine",
    "create_outbound_atomic",
]
