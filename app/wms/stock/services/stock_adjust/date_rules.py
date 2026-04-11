# app/wms/stock/services/stock_adjust/date_rules.py
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.shared.services.expiry_resolver import normalize_batch_dates_for_item


async def resolve_and_validate_dates_for_inbound(
    *,
    session: AsyncSession,
    item_id: int,
    delta: int,
    batch_code_norm: Optional[str],
    production_date: Optional[date],
    expiry_date: Optional[date],
) -> tuple[Optional[date], Optional[date]]:
    """
    入库侧日期裁决：

    - 有 batch_code 的路径，统一走 normalize_batch_dates_for_item
    - 不再私自用 date.today() 补 production_date
    - 对 delta>0（入库正增量），若最终仍无法形成 canonical production/expiry，则明确报错
    """
    pd = production_date
    ed = expiry_date

    if batch_code_norm is None:
        return None, None

    pd, ed, _resolution_mode = await normalize_batch_dates_for_item(
        session=session,
        item_id=item_id,
        production_date=pd,
        expiry_date=ed,
    )

    if delta > 0:
        if pd is None:
            raise ValueError(
                "批次受控商品必须提供 production_date，或提供可结合保质期反推出 production_date 的 expiry_date。"
            )
        if ed is None:
            raise ValueError(
                "未提供到期日期，且商品未配置可用于推算的保质期，无法形成 canonical expiry_date。"
            )

    if ed is not None and pd is not None and ed < pd:
        raise ValueError(f"expiry_date({ed}) < production_date({pd})")

    return pd, ed
