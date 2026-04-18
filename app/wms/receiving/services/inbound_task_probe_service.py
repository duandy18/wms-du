from __future__ import annotations

from app.pms.public.items.services.barcode_probe_service import BarcodeProbeService
from app.wms.receiving.contracts.probe import (
    InboundTaskProbeOut,
    InboundTaskProbeStatus,
)
from app.wms.receiving.repos.inbound_task_probe_repo import (
    InboundTaskProbeLine,
    get_inbound_task_probe_lines,
)


def _match_line(
    *,
    lines: list[InboundTaskProbeLine],
    item_id: int,
    item_uom_id: int | None,
) -> tuple[InboundTaskProbeStatus, InboundTaskProbeLine | None, str | None]:
    if item_uom_id is not None:
        exact = [ln for ln in lines if ln.item_id == item_id and ln.item_uom_id == item_uom_id]
        if len(exact) == 1:
            return InboundTaskProbeStatus.MATCHED, exact[0], None
        if len(exact) > 1:
            return (
                InboundTaskProbeStatus.AMBIGUOUS,
                None,
                "当前收货单存在多条相同商品包装任务行，无法自动命中。",
            )
        return (
            InboundTaskProbeStatus.UNMATCHED,
            None,
            "当前收货单不存在该商品包装。",
        )

    by_item = [ln for ln in lines if ln.item_id == item_id]
    if len(by_item) == 1:
        return InboundTaskProbeStatus.MATCHED, by_item[0], None
    if len(by_item) > 1:
        return (
            InboundTaskProbeStatus.AMBIGUOUS,
            None,
            "当前收货单存在同商品多包装任务行，条码未解析出包装，无法自动命中。",
        )
    return (
        InboundTaskProbeStatus.UNMATCHED,
        None,
        "当前收货单不存在该商品。",
    )


async def probe_inbound_task_barcode(
    session,
    *,
    receipt_no: str,
    barcode: str,
) -> InboundTaskProbeOut:
    code = (barcode or "").strip()
    lines = await get_inbound_task_probe_lines(session, receipt_no=receipt_no)

    probe = await BarcodeProbeService(session).aprobe(barcode=code)
    if probe.status != "BOUND" or probe.item_id is None:
        return InboundTaskProbeOut(
            ok=True,
            status=InboundTaskProbeStatus.UNBOUND,
            barcode=code,
            message="条码未绑定商品包装。",
        )

    item_id = int(probe.item_id)
    item_uom_id = int(probe.item_uom_id) if probe.item_uom_id is not None else None
    ratio_to_base = int(probe.ratio_to_base) if probe.ratio_to_base is not None else None

    status, matched, message = _match_line(
        lines=lines,
        item_id=item_id,
        item_uom_id=item_uom_id,
    )

    return InboundTaskProbeOut(
        ok=True,
        status=status,
        barcode=code,
        item_id=item_id,
        item_uom_id=item_uom_id,
        ratio_to_base=ratio_to_base,
        matched_line_no=(matched.line_no if matched else None),
        item_name_snapshot=(matched.item_name_snapshot if matched else None),
        uom_name_snapshot=(matched.uom_name_snapshot if matched else None),
        message=message,
    )


__all__ = [
    "probe_inbound_task_barcode",
]
