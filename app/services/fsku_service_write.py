# app/services/fsku_service_write.py
from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas.fsku import FskuComponentIn, FskuDetailOut
from app.models.fsku import Fsku, FskuComponent
from app.services.fsku_service_errors import FskuBadInput, FskuConflict, FskuNotFound
from app.services.fsku_service_mapper import to_detail
from app.services.fsku_service_utils import normalize_code, normalize_shape, utc_now


def _load_components(db: Session, fsku_id: int) -> list[FskuComponent]:
    return db.scalars(select(FskuComponent).where(FskuComponent.fsku_id == fsku_id)).all()


def _is_bound_by_merchant_codes(db: Session, fsku_id: int) -> bool:
    # ✅ current-only 绑定表：只要存在引用，就冻结生命周期终止（retire）
    row = db.execute(
        text("SELECT 1 FROM merchant_code_fsku_bindings WHERE fsku_id = :id LIMIT 1"),
        {"id": int(fsku_id)},
    ).first()
    return row is not None


def create_draft(db: Session, *, name: str, code: str | None, shape: str | None) -> FskuDetailOut:
    now = utc_now()
    shp = normalize_shape(shape)
    cd = normalize_code(code)

    obj = Fsku(
        name=name.strip(),
        code="__PENDING__",  # 临时占位，flush 后生成最终 code
        shape=shp,
        status="draft",
        created_at=now,
        updated_at=now,
    )
    db.add(obj)
    db.flush()  # 拿到 obj.id

    # ✅ code 规则：用户传入则用；否则生成 FSKU-{id}
    obj.code = cd or f"FSKU-{obj.id}"

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise FskuConflict("FSKU code 冲突（必须全局唯一）") from None

    db.refresh(obj)
    return to_detail(obj, [])


def update_name(db: Session, *, fsku_id: int, name: str) -> FskuDetailOut:
    obj = db.get(Fsku, fsku_id)
    if obj is None:
        raise FskuNotFound("FSKU 不存在")

    # ✅ 更保守：retired 只读（避免改历史）
    if obj.status == "retired":
        raise FskuConflict("FSKU 已退休，名称不可修改")

    nm = name.strip()
    if not nm:
        raise FskuBadInput(details=[{"type": "validation", "path": "name", "reason": "name 不能为空"}])

    now = utc_now()
    obj.name = nm
    obj.updated_at = now
    db.add(obj)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise FskuConflict("更新失败（状态冲突）") from None

    db.refresh(obj)
    comps = _load_components(db, fsku_id)
    return to_detail(obj, comps)


def replace_components_draft(db: Session, *, fsku_id: int, components: list[FskuComponentIn]) -> FskuDetailOut:
    obj = db.get(Fsku, fsku_id)
    if obj is None:
        raise FskuNotFound("FSKU 不存在")

    if obj.status != "draft":
        raise FskuConflict("FSKU 非草稿态，components 已冻结；如需改动请新建版本/新 FSKU")

    details: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()

    for i, c in enumerate(components):
        key = (c.item_id, str(c.role))
        if key in seen:
            details.append({"type": "validation", "path": f"components[{i}]", "reason": "重复的 item_id + role"})
        seen.add(key)

    if details:
        raise FskuBadInput(details=details)

    if not any(str(c.role) == "primary" for c in components):
        raise FskuBadInput(details=[{"type": "validation", "path": "components", "reason": "必须至少包含 1 条 role=primary（主销商品）"}])

    for i, c in enumerate(components):
        ok = db.execute(text("select 1 from items where id=:id"), {"id": c.item_id}).first()
        if ok is None:
            details.append({"type": "validation", "path": f"components[{i}].item_id", "reason": "Item 不存在"})
    if details:
        raise FskuBadInput(details=details)

    now = utc_now()

    db.execute(delete(FskuComponent).where(FskuComponent.fsku_id == fsku_id))

    for c in components:
        db.add(
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
    db.add(obj)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise FskuConflict("components 写入冲突，请重试") from None

    db.refresh(obj)
    comps = _load_components(db, fsku_id)
    return to_detail(obj, comps)


def publish(db: Session, fsku_id: int) -> FskuDetailOut:
    obj = db.get(Fsku, fsku_id)
    if obj is None:
        raise FskuNotFound("FSKU 不存在")

    if obj.status != "draft":
        raise FskuConflict("仅草稿态允许发布")

    total = int(db.scalar(select(func.count()).select_from(FskuComponent).where(FskuComponent.fsku_id == fsku_id)) or 0)
    if total <= 0:
        raise FskuConflict("发布前必须至少配置 1 个 component")

    primary_n = int(
        db.scalar(
            select(func.count())
            .select_from(FskuComponent)
            .where(FskuComponent.fsku_id == fsku_id, FskuComponent.role == "primary")
        )
        or 0
    )
    if primary_n <= 0:
        raise FskuConflict("发布前必须至少包含 1 条 role=primary（主销商品）")

    now = utc_now()
    obj.status = "published"
    obj.published_at = now
    obj.updated_at = now

    db.add(obj)
    db.commit()
    db.refresh(obj)

    comps = _load_components(db, fsku_id)
    return to_detail(obj, comps)


def retire(db: Session, fsku_id: int) -> FskuDetailOut:
    obj = db.get(Fsku, fsku_id)
    if obj is None:
        raise FskuNotFound("FSKU 不存在")

    if obj.status != "published":
        raise FskuConflict("仅已发布的 FSKU 允许停用")

    # ✅ 冻结护栏：被 merchant_code 绑定引用时禁止退休
    if _is_bound_by_merchant_codes(db, fsku_id):
        raise FskuConflict("该 FSKU 正在被店铺商品代码引用（存在绑定），请先改绑/解绑后再退休")

    now = utc_now()
    obj.status = "retired"
    obj.retired_at = now
    obj.updated_at = now

    db.add(obj)
    db.commit()
    db.refresh(obj)

    comps = _load_components(db, fsku_id)
    return to_detail(obj, comps)


def unretire(db: Session, fsku_id: int) -> FskuDetailOut:
    # ✅ 封板：生命周期单向，发布事实不可逆；保留 endpoint 仅用于兼容，但永远 409
    _ = fsku_id
    raise FskuConflict("系统不支持取消归档：FSKU 生命周期单向（draft → published → retired）")
