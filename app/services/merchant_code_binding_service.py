# app/services/merchant_code_binding_service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fsku import Fsku
from app.models.merchant_code_fsku_binding import MerchantCodeFskuBinding


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_merchant_code(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = v.strip()
    return s or None


class MerchantCodeBindingService:
    class NotFound(Exception):
        pass

    class Conflict(Exception):
        pass

    @dataclass
    class BadInput(Exception):
        message: str

    def __init__(self, session: AsyncSession):
        self.session = session

    async def bind_current(
        self,
        *,
        platform: str,
        shop_id: int,
        merchant_code: str,
        fsku_id: int,
        reason: Optional[str],
    ) -> MerchantCodeFskuBinding:
        cd = normalize_merchant_code(merchant_code)
        if cd is None:
            raise self.BadInput("merchant_code 不能为空")

        f = await self.session.get(Fsku, int(fsku_id))
        if f is None:
            raise self.NotFound("FSKU 不存在")
        if f.status != "published":
            raise self.Conflict("仅 published FSKU 允许绑定（避免草稿/退休被订单引用）")

        now = _utc_now()

        # 关闭旧 current
        await self.session.execute(
            update(MerchantCodeFskuBinding)
            .where(
                MerchantCodeFskuBinding.platform == platform,
                MerchantCodeFskuBinding.shop_id == int(shop_id),
                MerchantCodeFskuBinding.merchant_code == cd,
                MerchantCodeFskuBinding.effective_to.is_(None),
            )
            .values(effective_to=now)
        )

        obj = MerchantCodeFskuBinding(
            platform=platform,
            shop_id=int(shop_id),
            merchant_code=cd,
            fsku_id=int(fsku_id),
            effective_from=now,
            effective_to=None,
            reason=(reason.strip() if reason else None),
            created_at=now,
        )
        self.session.add(obj)

        # 这里让 unique partial index 作为最终裁决（并发下会抛错）
        await self.session.flush()
        return obj

    async def resolve_fsku_id(
        self, *, platform: str, shop_id: int, merchant_code: Optional[str]
    ) -> tuple[bool, str | None, int | None]:
        """
        返回：(ok, error_code, fsku_id)
        error_code:
          - MISSING_CODE
          - INVALID_CODE_FORMAT
          - CODE_NOT_BOUND
          - FSKU_NOT_PUBLISHED
        """
        cd = normalize_merchant_code(merchant_code)
        if cd is None:
            return (False, "MISSING_CODE", None)
        if len(cd) > 128:
            return (False, "INVALID_CODE_FORMAT", None)

        row = (
            await self.session.execute(
                select(MerchantCodeFskuBinding)
                .where(
                    MerchantCodeFskuBinding.platform == platform,
                    MerchantCodeFskuBinding.shop_id == int(shop_id),
                    MerchantCodeFskuBinding.merchant_code == cd,
                    MerchantCodeFskuBinding.effective_to.is_(None),
                )
                .limit(1)
            )
        ).scalars().first()

        if row is None:
            return (False, "CODE_NOT_BOUND", None)

        f = await self.session.get(Fsku, int(row.fsku_id))
        if f is None:
            return (False, "CODE_NOT_BOUND", None)
        if f.status != "published":
            return (False, "FSKU_NOT_PUBLISHED", None)

        return (True, None, int(row.fsku_id))
