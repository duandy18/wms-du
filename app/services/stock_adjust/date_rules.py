# app/services/stock_adjust/date_rules.py
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.utils.expiry_resolver import resolve_batch_dates_for_item


async def resolve_and_validate_dates_for_inbound(
    *,
    session: AsyncSession,
    item_id: int,
    delta: int,
    batch_code_norm: Optional[str],
    production_date: Optional[date],
    expiry_date: Optional[date],
) -> tuple[Optional[date], Optional[date]]:
    pd = production_date
    ed = expiry_date

    if delta > 0 and batch_code_norm is not None:
        if pd is None and ed is None:
            pd = pd or date.today()

        pd, ed = await resolve_batch_dates_for_item(
            session=session,
            item_id=item_id,
            production_date=pd,
            expiry_date=ed,
        )

        if ed is not None and pd is not None:
            if ed < pd:
                raise ValueError(f"expiry_date({ed}) < production_date({pd})")

    if batch_code_norm is None:
        pd = None
        ed = None

    return pd, ed
