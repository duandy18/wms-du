# app/services/merchant_code_binding_service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, select, update
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


def normalize_shop_id(v: str | int | None) -> str | None:
    if v is None:
        return None
    if isinstance(v, int):
        return str(v)
    s = str(v).strip()
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

    async def bind_upsert(
        self,
        *,
        platform: str,
        shop_id: str,
        merchant_code: str,
        fsku_id: int,
        reason: Optional[str],
    ) -> MerchantCodeFskuBinding:
        """
        一码一对一：同一 (platform, shop_id, merchant_code) 永远只有一条记录。
        - 若存在：覆盖 fsku_id / reason / updated_at
        - 若不存在：插入 created_at/updated_at
        """
        cd = normalize_merchant_code(merchant_code)
        if cd is None:
            raise self.BadInput("merchant_code 不能为空")

        sid = normalize_shop_id(shop_id)
        if sid is None:
            raise self.BadInput("shop_id 不能为空")

        f = await self.session.get(Fsku, int(fsku_id))
        if f is None:
            raise self.NotFound("FSKU 不存在")
        if f.status != "published":
            raise self.Conflict("仅 published FSKU 允许绑定（避免草稿/退休被订单引用）")

        now = _utc_now()
        rsn = reason.strip() if reason else None

        row = (
            (
                await self.session.execute(
                    select(MerchantCodeFskuBinding).where(
                        MerchantCodeFskuBinding.platform == platform,
                        MerchantCodeFskuBinding.shop_id == sid,
                        MerchantCodeFskuBinding.merchant_code == cd,
                    )
                )
            )
            .scalars()
            .first()
        )

        if row is None:
            obj = MerchantCodeFskuBinding(
                platform=platform,
                shop_id=sid,
                merchant_code=cd,
                fsku_id=int(fsku_id),
                reason=rsn,
                created_at=now,
                updated_at=now,
            )
            self.session.add(obj)
            await self.session.flush()
            return obj

        # 覆盖更新（不改 created_at）
        await self.session.execute(
            update(MerchantCodeFskuBinding)
            .where(MerchantCodeFskuBinding.id == int(row.id))
            .values(
                fsku_id=int(fsku_id),
                reason=rsn,
                updated_at=now,
            )
        )
        await self.session.flush()
        return row

    async def unbind(
        self,
        *,
        platform: str,
        shop_id: str,
        merchant_code: str,
    ) -> MerchantCodeFskuBinding:
        """
        解绑：delete by unique key。
        返回被删除的那条记录（用于 API 输出 join 信息）。
        """
        cd = normalize_merchant_code(merchant_code)
        if cd is None:
            raise self.BadInput("merchant_code 不能为空")

        sid = normalize_shop_id(shop_id)
        if sid is None:
            raise self.BadInput("shop_id 不能为空")

        row = (
            (
                await self.session.execute(
                    select(MerchantCodeFskuBinding).where(
                        MerchantCodeFskuBinding.platform == platform,
                        MerchantCodeFskuBinding.shop_id == sid,
                        MerchantCodeFskuBinding.merchant_code == cd,
                    )
                )
            )
            .scalars()
            .first()
        )

        if row is None:
            raise self.NotFound("未找到可解绑的绑定")

        await self.session.execute(delete(MerchantCodeFskuBinding).where(MerchantCodeFskuBinding.id == int(row.id)))
        await self.session.flush()
        return row

    async def resolve_fsku_id(
        self, *, platform: str, shop_id: str, merchant_code: Optional[str]
    ) -> tuple[bool, str | None, int | None]:
        cd = normalize_merchant_code(merchant_code)
        if cd is None:
            return (False, "MISSING_CODE", None)
        if len(cd) > 128:
            return (False, "INVALID_CODE_FORMAT", None)

        sid = normalize_shop_id(shop_id)
        if sid is None:
            return (False, "MISSING_CODE", None)

        row = (
            (
                await self.session.execute(
                    select(MerchantCodeFskuBinding).where(
                        MerchantCodeFskuBinding.platform == platform,
                        MerchantCodeFskuBinding.shop_id == sid,
                        MerchantCodeFskuBinding.merchant_code == cd,
                    )
                )
            )
            .scalars()
            .first()
        )

        if row is None:
            return (False, "CODE_NOT_BOUND", None)

        f = await self.session.get(Fsku, int(row.fsku_id))
        if f is None:
            return (False, "CODE_NOT_BOUND", None)
        if f.status != "published":
            return (False, "FSKU_NOT_PUBLISHED", None)

        return (True, None, int(row.fsku_id))
