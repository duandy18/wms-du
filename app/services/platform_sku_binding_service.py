# app/services/platform_sku_binding_service.py
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas.platform_sku_binding import (
    BindingCurrentOut,
    BindingHistoryOut,
    BindingMigrateOut,
    BindingRow,
)
from app.models.fsku import Fsku
from app.models.platform_sku_binding import PlatformSkuBinding


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PlatformSkuBindingService:
    class NotFound(Exception):
        pass

    class Conflict(Exception):
        pass

    def __init__(self, db: Session):
        self.db = db

    def get_current(self, *, platform: str, shop_id: int, platform_sku_id: str) -> BindingCurrentOut | None:
        row = self.db.scalars(
            select(PlatformSkuBinding)
            .where(
                PlatformSkuBinding.platform == platform,
                PlatformSkuBinding.shop_id == shop_id,
                PlatformSkuBinding.platform_sku_id == platform_sku_id,
                PlatformSkuBinding.effective_to.is_(None),
            )
            .order_by(PlatformSkuBinding.effective_from.desc())
        ).first()

        if row is None:
            return None

        return BindingCurrentOut(current=self._to_row(row))

    def get_history(
        self, *, platform: str, shop_id: int, platform_sku_id: str, limit: int, offset: int
    ) -> BindingHistoryOut:
        base = (
            select(PlatformSkuBinding)
            .where(
                PlatformSkuBinding.platform == platform,
                PlatformSkuBinding.shop_id == shop_id,
                PlatformSkuBinding.platform_sku_id == platform_sku_id,
            )
            .order_by(PlatformSkuBinding.effective_from.desc())
        )

        total = int(self.db.scalar(select(func.count()).select_from(base.subquery())) or 0)
        rows = self.db.scalars(base.limit(limit).offset(offset)).all()

        return BindingHistoryOut(items=[self._to_row(r) for r in rows], total=total, limit=limit, offset=offset)

    def bind(
        self,
        *,
        platform: str,
        shop_id: int,
        platform_sku_id: str,
        fsku_id: int,
        reason: str | None,
    ) -> BindingCurrentOut:
        # ✅ 单入口：仅允许绑定 FSKU
        fsku = self.db.get(Fsku, fsku_id)
        if fsku is None:
            raise self.NotFound("FSKU 不存在")
        if fsku.status != "published":
            raise self.Conflict("仅允许绑定到已发布的 FSKU")

        now = _utc_now()

        # 关闭旧 current（如存在）
        self.db.execute(
            update(PlatformSkuBinding)
            .where(
                PlatformSkuBinding.platform == platform,
                PlatformSkuBinding.shop_id == shop_id,
                PlatformSkuBinding.platform_sku_id == platform_sku_id,
                PlatformSkuBinding.effective_to.is_(None),
            )
            .values(effective_to=now)
        )

        # 插入新 current（历史不可篡改：不 update 旧行目标）
        new_row = PlatformSkuBinding(
            platform=platform,
            shop_id=shop_id,
            platform_sku_id=platform_sku_id,
            item_id=None,  # ✅ 强制单入口
            fsku_id=fsku_id,
            effective_from=now,
            effective_to=None,
            reason=reason,
            created_at=now,
        )
        self.db.add(new_row)

        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise self.Conflict("绑定写入冲突，请重试")

        self.db.refresh(new_row)
        return BindingCurrentOut(current=self._to_row(new_row))

    def unbind(self, *, platform: str, shop_id: int, platform_sku_id: str, reason: str | None) -> None:
        # 解除绑定：只关闭 current，不插入新行
        now = _utc_now()

        cur = self.db.scalars(
            select(PlatformSkuBinding)
            .where(
                PlatformSkuBinding.platform == platform,
                PlatformSkuBinding.shop_id == shop_id,
                PlatformSkuBinding.platform_sku_id == platform_sku_id,
                PlatformSkuBinding.effective_to.is_(None),
            )
            .order_by(PlatformSkuBinding.effective_from.desc())
        ).first()

        if cur is None:
            raise self.NotFound("当前无生效绑定，无法解除")

        cur.effective_to = now
        if reason is not None:
            cur.reason = reason

        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise self.Conflict("解除绑定写入冲突，请重试")

    def migrate(self, *, binding_id: int, to_fsku_id: int, reason: str | None) -> BindingMigrateOut:
        row = self.db.get(PlatformSkuBinding, binding_id)
        if row is None:
            raise self.NotFound("Binding 不存在")

        cur = self.get_current(platform=row.platform, shop_id=row.shop_id, platform_sku_id=row.platform_sku_id)
        if cur is None:
            raise self.Conflict("当前无生效绑定，无法迁移")

        # 目标一致：直接返回
        if cur.current.fsku_id == to_fsku_id:
            return BindingMigrateOut(current=cur.current)

        out = self.bind(
            platform=row.platform,
            shop_id=row.shop_id,
            platform_sku_id=row.platform_sku_id,
            fsku_id=to_fsku_id,
            reason=reason,
        )
        return BindingMigrateOut(current=out.current)

    def _to_row(self, r: PlatformSkuBinding) -> BindingRow:
        return BindingRow(
            id=r.id,
            platform=r.platform,
            shop_id=r.shop_id,
            platform_sku_id=r.platform_sku_id,
            item_id=r.item_id,  # legacy 读历史允许存在
            fsku_id=r.fsku_id,
            effective_from=r.effective_from,
            effective_to=r.effective_to,
            reason=r.reason,
        )
