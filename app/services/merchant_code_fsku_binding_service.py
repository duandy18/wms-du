# app/services/merchant_code_fsku_binding_service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.schemas.merchant_code_fsku_binding import (
    MerchantCodeBindingOut,
    MerchantCodeResolveResult,
)
from app.models.fsku import Fsku
from app.models.merchant_code_fsku_binding import MerchantCodeFskuBinding


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_merchant_code(v: str | None) -> str | None:
    if v is None:
        return None
    s = v.strip()
    if not s:
        return None
    # 这里先不做“智能纠错”，只做最低限度的 normalize
    # 后续如需：全角半角 / 大小写统一，可在这里加，但要保持 deterministic
    return s


class MerchantCodeFskuBindingService:
    class Conflict(Exception):
        pass

    class NotFound(Exception):
        pass

    @dataclass
    class BadInput(Exception):
        message: str

    def __init__(self, db: Session):
        self.db = db

    def resolve_fsku_id(
        self, *, platform: str, shop_id: int, merchant_code: str | None
    ) -> MerchantCodeResolveResult:
        cd = normalize_merchant_code(merchant_code)
        if cd is None:
            return MerchantCodeResolveResult(ok=False, error="MISSING_CODE")

        # 极简格式校验：你们如果有更严格规则（比如必须以 FSKU- 开头），可以在这里收紧
        if len(cd) > 128:
            return MerchantCodeResolveResult(ok=False, error="INVALID_CODE_FORMAT")

        row = self.db.execute(
            select(MerchantCodeFskuBinding)
            .where(
                MerchantCodeFskuBinding.platform == platform,
                MerchantCodeFskuBinding.shop_id == shop_id,
                MerchantCodeFskuBinding.merchant_code == cd,
                MerchantCodeFskuBinding.effective_to.is_(None),
            )
            .limit(1)
        ).scalar_one_or_none()

        if row is None:
            return MerchantCodeResolveResult(ok=False, error="CODE_NOT_BOUND")

        # 防御：理论上写入时封死，但读时仍要校验 published
        f = self.db.get(Fsku, row.fsku_id)
        if f is None:
            return MerchantCodeResolveResult(ok=False, error="CODE_NOT_BOUND")
        if f.status != "published":
            return MerchantCodeResolveResult(ok=False, error="FSKU_NOT_PUBLISHED")

        return MerchantCodeResolveResult(ok=True, fsku_id=row.fsku_id)

    def bind_current(
        self,
        *,
        platform: str,
        shop_id: int,
        merchant_code: str,
        fsku_id: int,
        reason: str | None,
    ) -> MerchantCodeBindingOut:
        cd = normalize_merchant_code(merchant_code)
        if cd is None:
            raise self.BadInput("merchant_code 不能为空")

        f = self.db.get(Fsku, fsku_id)
        if f is None:
            raise self.NotFound("FSKU 不存在")
        if f.status != "published":
            raise self.Conflict("仅 published FSKU 允许绑定（避免草稿/退休被订单引用）")

        now = _utc_now()

        # 关闭旧 current（如果存在）
        self.db.execute(
            update(MerchantCodeFskuBinding)
            .where(
                MerchantCodeFskuBinding.platform == platform,
                MerchantCodeFskuBinding.shop_id == shop_id,
                MerchantCodeFskuBinding.merchant_code == cd,
                MerchantCodeFskuBinding.effective_to.is_(None),
            )
            .values(effective_to=now)
        )

        obj = MerchantCodeFskuBinding(
            platform=platform,
            shop_id=shop_id,
            merchant_code=cd,
            fsku_id=fsku_id,
            effective_from=now,
            effective_to=None,
            reason=(reason.strip() if reason else None),
            created_at=now,
        )
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)

        return MerchantCodeBindingOut(
            id=obj.id,
            platform=obj.platform,
            shop_id=obj.shop_id,
            merchant_code=obj.merchant_code,
            fsku_id=obj.fsku_id,
            effective_from=obj.effective_from,
            effective_to=obj.effective_to,
            reason=obj.reason,
            created_at=obj.created_at,
        )
