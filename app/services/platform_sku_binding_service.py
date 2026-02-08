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


def _norm_platform(v: str) -> str:
    # ✅ 与 resolver 一致：平台代码统一 upper+strip
    return (v or "").strip().upper()


def _norm_psku(v: str) -> str:
    # ✅ PSKU 入口统一 strip（空字符串在上层 schema 已禁止，但这里仍做兜底）
    return (v or "").strip()


class PlatformSkuBindingService:
    class NotFound(Exception):
        pass

    class Conflict(Exception):
        pass

    def __init__(self, db: Session):
        self.db = db

    def get_current(self, *, platform: str, store_id: int, platform_sku_id: str) -> BindingCurrentOut | None:
        plat = _norm_platform(platform)
        psku = _norm_psku(platform_sku_id)

        row = self.db.scalars(
            select(PlatformSkuBinding)
            .where(
                PlatformSkuBinding.platform == plat,
                PlatformSkuBinding.store_id == store_id,
                PlatformSkuBinding.platform_sku_id == psku,
                PlatformSkuBinding.effective_to.is_(None),
            )
            .order_by(PlatformSkuBinding.effective_from.desc())
        ).first()

        if row is None:
            return None

        return BindingCurrentOut(current=self._to_row(row))

    def get_history(
        self, *, platform: str, store_id: int, platform_sku_id: str, limit: int, offset: int
    ) -> BindingHistoryOut:
        plat = _norm_platform(platform)
        psku = _norm_psku(platform_sku_id)

        base = (
            select(PlatformSkuBinding)
            .where(
                PlatformSkuBinding.platform == plat,
                PlatformSkuBinding.store_id == store_id,
                PlatformSkuBinding.platform_sku_id == psku,
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
        store_id: int,
        platform_sku_id: str,
        fsku_id: int,
        reason: str | None,
    ) -> BindingCurrentOut:
        plat = _norm_platform(platform)
        psku = _norm_psku(platform_sku_id)

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
                PlatformSkuBinding.platform == plat,
                PlatformSkuBinding.store_id == store_id,
                PlatformSkuBinding.platform_sku_id == psku,
                PlatformSkuBinding.effective_to.is_(None),
            )
            .values(effective_to=now)
        )

        # 插入新 current（历史不可篡改：不 update 旧行目标）
        new_row = PlatformSkuBinding(
            platform=plat,
            store_id=store_id,
            platform_sku_id=psku,
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

    def unbind(self, *, platform: str, store_id: int, platform_sku_id: str, reason: str | None) -> None:
        plat = _norm_platform(platform)
        psku = _norm_psku(platform_sku_id)

        # 解除绑定：只关闭 current，不插入新行
        now = _utc_now()

        cur = self.db.scalars(
            select(PlatformSkuBinding)
            .where(
                PlatformSkuBinding.platform == plat,
                PlatformSkuBinding.store_id == store_id,
                PlatformSkuBinding.platform_sku_id == psku,
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

        # row.platform / row.platform_sku_id 以 DB 为准，但仍走规范化以确保一致
        plat = _norm_platform(row.platform)
        psku = _norm_psku(row.platform_sku_id)

        cur = self.get_current(platform=plat, store_id=row.store_id, platform_sku_id=psku)
        if cur is None:
            raise self.Conflict("当前无生效绑定，无法迁移")

        # 目标一致：直接返回
        if cur.current.fsku_id == to_fsku_id:
            return BindingMigrateOut(current=cur.current)

        out = self.bind(
            platform=plat,
            store_id=row.store_id,
            platform_sku_id=psku,
            fsku_id=to_fsku_id,
            reason=reason,
        )
        return BindingMigrateOut(current=out.current)

    def _to_row(self, r: PlatformSkuBinding) -> BindingRow:
        # ✅ 合同升级：输出同时带 store_id + shop_id（兼容）
        # - 二者语义一致（stores.id）
        return BindingRow(
            id=r.id,
            platform=str(r.platform or "").strip().lower(),
            store_id=r.store_id,
            shop_id=r.store_id,
            platform_sku_id=r.platform_sku_id,
            item_id=r.item_id,  # legacy 读历史允许存在
            fsku_id=r.fsku_id,
            effective_from=r.effective_from,
            effective_to=r.effective_to,
            reason=r.reason,
        )
