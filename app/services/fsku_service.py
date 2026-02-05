# app/services/fsku_service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas.fsku import (
    FskuComponentIn,
    FskuComponentOut,
    FskuDetailOut,
    FskuListItem,
    FskuListOut,
)
from app.models.fsku import Fsku, FskuComponent


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FskuService:
    class NotFound(Exception):
        pass

    class Conflict(Exception):
        pass

    @dataclass
    class BadInput(Exception):
        details: list[dict[str, Any]]

    def __init__(self, db: Session):
        self.db = db

    def create_draft(self, *, name: str, unit_label: str | None) -> FskuDetailOut:
        now = _utc_now()
        obj = Fsku(
            name=name.strip(),
            unit_label=(unit_label.strip() if unit_label else None),
            status="draft",
            created_at=now,
            updated_at=now,
        )
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return self._to_detail(obj, [])

    def list_fskus(self, *, query: str | None, status: str | None, limit: int, offset: int) -> FskuListOut:
        stmt = select(Fsku)
        if query:
            q = f"%{query.strip()}%"
            stmt = stmt.where(Fsku.name.ilike(q))
        if status:
            stmt = stmt.where(Fsku.status == status)

        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = self.db.scalars(stmt.order_by(Fsku.updated_at.desc()).limit(limit).offset(offset)).all()

        items = [
            FskuListItem(
                id=r.id,
                name=r.name,
                unit_label=r.unit_label,
                status=r.status,
                updated_at=r.updated_at,
            )
            for r in rows
        ]
        return FskuListOut(items=items, total=total, limit=limit, offset=offset)

    def get_detail(self, fsku_id: int) -> FskuDetailOut | None:
        obj = self.db.get(Fsku, fsku_id)
        if obj is None:
            return None
        comps = self.db.scalars(select(FskuComponent).where(FskuComponent.fsku_id == fsku_id)).all()
        return self._to_detail(obj, comps)

    def replace_components_draft(self, *, fsku_id: int, components: list[FskuComponentIn]) -> FskuDetailOut:
        obj = self.db.get(Fsku, fsku_id)
        if obj is None:
            raise self.NotFound("FSKU 不存在")

        if obj.status != "draft":
            raise self.Conflict("FSKU 非草稿态，components 已冻结；如需改动请新建版本/新 FSKU")

        details: list[dict[str, Any]] = []
        seen: set[tuple[int, str]] = set()

        for i, c in enumerate(components):
            key = (c.item_id, c.role)
            if key in seen:
                details.append({"type": "validation", "path": f"components[{i}]", "reason": "重复的 item_id + role"})
            seen.add(key)

        if details:
            raise self.BadInput(details=details)

        # ✅ 明确校验 item_id 存在（避免 FK 报错变 500）
        # 不引入 Item ORM，直接查 items 表存在性
        for i, c in enumerate(components):
            ok = self.db.execute(text("select 1 from items where id=:id"), {"id": c.item_id}).first()
            if ok is None:
                details.append({"type": "validation", "path": f"components[{i}].item_id", "reason": "Item 不存在"})
        if details:
            raise self.BadInput(details=details)

        now = _utc_now()

        # 全量替换：先删再插
        self.db.execute(delete(FskuComponent).where(FskuComponent.fsku_id == fsku_id))

        for c in components:
            self.db.add(
                FskuComponent(
                    fsku_id=fsku_id,
                    item_id=c.item_id,
                    qty=Decimal(str(c.qty)),
                    role=c.role,
                    created_at=now,
                    updated_at=now,
                )
            )

        obj.updated_at = now
        self.db.add(obj)

        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise self.Conflict("components 写入冲突，请重试")

        self.db.refresh(obj)
        comps = self.db.scalars(select(FskuComponent).where(FskuComponent.fsku_id == fsku_id)).all()
        return self._to_detail(obj, comps)

    def publish(self, fsku_id: int) -> FskuDetailOut:
        obj = self.db.get(Fsku, fsku_id)
        if obj is None:
            raise self.NotFound("FSKU 不存在")

        if obj.status != "draft":
            raise self.Conflict("仅草稿态允许发布")

        n = int(
            self.db.scalar(select(func.count()).select_from(FskuComponent).where(FskuComponent.fsku_id == fsku_id)) or 0
        )
        if n <= 0:
            raise self.Conflict("发布前必须至少配置 1 个 component")

        now = _utc_now()
        obj.status = "published"
        obj.published_at = now
        obj.updated_at = now

        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)

        comps = self.db.scalars(select(FskuComponent).where(FskuComponent.fsku_id == fsku_id)).all()
        return self._to_detail(obj, comps)

    def retire(self, fsku_id: int) -> FskuDetailOut:
        obj = self.db.get(Fsku, fsku_id)
        if obj is None:
            raise self.NotFound("FSKU 不存在")

        if obj.status != "published":
            raise self.Conflict("仅已发布的 FSKU 允许停用")

        now = _utc_now()
        obj.status = "retired"
        obj.retired_at = now
        obj.updated_at = now

        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)

        comps = self.db.scalars(select(FskuComponent).where(FskuComponent.fsku_id == fsku_id)).all()
        return self._to_detail(obj, comps)

    def _to_detail(self, f: Fsku, components: list[FskuComponent]) -> FskuDetailOut:
        out_components = [FskuComponentOut(item_id=c.item_id, qty=float(c.qty), role=c.role) for c in components]
        return FskuDetailOut(
            id=f.id,
            name=f.name,
            unit_label=f.unit_label,
            status=f.status,
            published_at=f.published_at,
            retired_at=f.retired_at,
            created_at=f.created_at,
            updated_at=f.updated_at,
            components=out_components,
        )
