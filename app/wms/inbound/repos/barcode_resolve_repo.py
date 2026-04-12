# app/wms/inbound/repos/barcode_resolve_repo.py
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.pms.public.items.services.barcode_probe_service import BarcodeProbeService


@dataclass(frozen=True)
class InboundBarcodeResolved:
    """
    入库条码解析结果。

    说明：
    - 这是 WMS inbound 对 PMS public barcode probe 的轻包装
    - 只承载入库提交链真正需要的最小字段
    - 不承载 qty / event_id / lot 等仓内执行语义
    """

    item_id: int
    item_uom_id: int | None
    ratio_to_base: int | None
    symbology: str | None
    active: bool | None


async def resolve_inbound_barcode(
    session: AsyncSession,
    *,
    barcode: str,
) -> InboundBarcodeResolved | None:
    """
    通过 PMS public barcode probe 解析入库条码。

    规则：
    - 空条码 => None
    - 未绑定/异常 => None
    - 已绑定 => 返回 item_id / item_uom_id / ratio_to_base 等最小结果
    """
    code = (barcode or "").strip()
    if not code:
        return None

    probe = await BarcodeProbeService(session).aprobe(barcode=code)
    if probe.status != "BOUND":
        return None
    if probe.item_id is None:
        return None

    return InboundBarcodeResolved(
        item_id=int(probe.item_id),
        item_uom_id=(
            int(probe.item_uom_id) if probe.item_uom_id is not None else None
        ),
        ratio_to_base=(
            int(probe.ratio_to_base) if probe.ratio_to_base is not None else None
        ),
        symbology=str(probe.symbology) if probe.symbology is not None else None,
        active=bool(probe.active) if probe.active is not None else None,
    )


__all__ = [
    "InboundBarcodeResolved",
    "resolve_inbound_barcode",
]
