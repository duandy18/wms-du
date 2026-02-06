# app/services/fsku_service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal

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


FskuShape = Literal["single", "bundle"]


def _normalize_shape(v: str | None) -> FskuShape:
    if v is None:
        return "bundle"
    s = v.strip()
    if not s:
        return "bundle"
    if s not in ("single", "bundle"):
        raise ValueError("shape must be 'single' or 'bundle'")
    return s  # type: ignore[return-value]


def _normalize_code(v: str | None) -> str | None:
    if v is None:
        return None
    s = v.strip()
    return s or None


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

    def create_draft(self, *, name: str, code: str | None, shape: str | None) -> FskuDetailOut:
        now = _utc_now()
        shp = _normalize_shape(shape)
        cd = _normalize_code(code)

        obj = Fsku(
            name=name.strip(),
            code="__PENDING__",  # 临时占位，flush 后生成最终 code
            shape=shp,
            status="draft",
            created_at=now,
            updated_at=now,
        )
        self.db.add(obj)
        self.db.flush()  # 拿到 obj.id

        # ✅ code 规则：用户传入则用；否则生成 FSKU-{id}
        obj.code = cd or f"FSKU-{obj.id}"

        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise self.Conflict("FSKU code 冲突（必须全局唯一）")
        self.db.refresh(obj)
        return self._to_detail(obj, [])

    def list_fskus(self, *, query: str | None, status: str | None, limit: int, offset: int) -> FskuListOut:
        base = select(Fsku.id)
        if query:
            q = f"%{query.strip()}%"
            base = base.where(Fsku.name.ilike(q) | Fsku.code.ilike(q))
        if status:
            base = base.where(Fsku.status == status)

        total = int(self.db.scalar(select(func.count()).select_from(base.subquery())) or 0)

        sql = """
        SELECT
          f.id,
          f.code,
          f.name,
          f.shape,
          f.status,
          f.updated_at,
          f.published_at,
          f.retired_at,
          COALESCE(
            STRING_AGG(
              (i.sku || '×' || (c.qty::int)::text || '(' || c.role || ')'),
              ' + '
              ORDER BY c.role, i.sku
            ),
            ''
          ) AS components_summary
        FROM fskus f
        LEFT JOIN fsku_components c ON c.fsku_id = f.id
        LEFT JOIN items i ON i.id = c.item_id
        WHERE 1=1
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}

        if query:
            sql += " AND (f.name ILIKE :q OR f.code ILIKE :q) "
            params["q"] = f"%{query.strip()}%"

        if status:
            sql += " AND f.status = :status "
            params["status"] = status

        sql += """
        GROUP BY f.id
        ORDER BY f.updated_at DESC
        LIMIT :limit OFFSET :offset
        """

        rows = self.db.execute(text(sql), params).mappings().all()

        items = [
            FskuListItem(
                id=int(r["id"]),
                code=str(r["code"]),
                name=str(r["name"]),
                shape=str(r["shape"]),
                status=str(r["status"]),
                updated_at=r["updated_at"],
                published_at=r["published_at"],
                retired_at=r["retired_at"],
                components_summary=str(r["components_summary"] or ""),
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

    def update_name(self, *, fsku_id: int, name: str) -> FskuDetailOut:
        obj = self.db.get(Fsku, fsku_id)
        if obj is None:
            raise self.NotFound("FSKU 不存在")

        # ✅ 更保守：retired 只读（运营避免改历史）
        if obj.status == "retired":
            raise self.Conflict("FSKU 已退休，名称不可修改")

        nm = name.strip()
        if not nm:
            raise self.BadInput(details=[{"type": "validation", "path": "name", "reason": "name 不能为空"}])

        now = _utc_now()
        obj.name = nm
        obj.updated_at = now
        self.db.add(obj)

        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise self.Conflict("更新失败（状态冲突）")

        self.db.refresh(obj)
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
            key = (c.item_id, str(c.role))
            if key in seen:
                details.append({"type": "validation", "path": f"components[{i}]", "reason": "重复的 item_id + role"})
            seen.add(key)

        if details:
            raise self.BadInput(details=details)

        if not any(str(c.role) == "primary" for c in components):
            raise self.BadInput(details=[{"type": "validation", "path": "components", "reason": "必须至少包含 1 条 role=primary（主销商品）"}])

        for i, c in enumerate(components):
            ok = self.db.execute(text("select 1 from items where id=:id"), {"id": c.item_id}).first()
            if ok is None:
                details.append({"type": "validation", "path": f"components[{i}].item_id", "reason": "Item 不存在"})
        if details:
            raise self.BadInput(details=details)

        now = _utc_now()

        self.db.execute(delete(FskuComponent).where(FskuComponent.fsku_id == fsku_id))

        for c in components:
            self.db.add(
                FskuComponent(
                    fsku_id=fsku_id,
                    item_id=c.item_id,
                    qty=Decimal(str(c.qty)),
                    role=str(c.role),
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

        total = int(
            self.db.scalar(select(func.count()).select_from(FskuComponent).where(FskuComponent.fsku_id == fsku_id)) or 0
        )
        if total <= 0:
            raise self.Conflict("发布前必须至少配置 1 个 component")

        primary_n = int(
            self.db.scalar(
                select(func.count())
                .select_from(FskuComponent)
                .where(FskuComponent.fsku_id == fsku_id, FskuComponent.role == "primary")
            )
            or 0
        )
        if primary_n <= 0:
            raise self.Conflict("发布前必须至少包含 1 条 role=primary（主销商品）")

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

    def unretire(self, fsku_id: int) -> FskuDetailOut:
        obj = self.db.get(Fsku, fsku_id)
        if obj is None:
            raise self.NotFound("FSKU 不存在")

        if obj.status != "retired":
            raise self.Conflict("仅已归档（retired）的 FSKU 允许取消归档")

        now = _utc_now()
        obj.status = "published"
        obj.retired_at = None
        obj.updated_at = now

        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)

        comps = self.db.scalars(select(FskuComponent).where(FskuComponent.fsku_id == fsku_id)).all()
        return self._to_detail(obj, comps)

    def _to_detail(self, f: Fsku, components: list[FskuComponent]) -> FskuDetailOut:
        out_components = [FskuComponentOut(item_id=c.item_id, qty=int(c.qty), role=c.role) for c in components]
        return FskuDetailOut(
            id=f.id,
            code=f.code,
            name=f.name,
            shape=f.shape,
            status=f.status,
            published_at=f.published_at,
            retired_at=f.retired_at,
            created_at=f.created_at,
            updated_at=f.updated_at,
            components=out_components,
        )
