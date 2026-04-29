# app/pms/sku_coding/routers/sku_coding.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.pms.sku_coding.contracts.sku_coding import (
    ListOut,
    SkuCodeTermCreate,
    SkuCodeTermGroupOut,
    SkuCodeTermOut,
    SkuCodeTermUpdate,
    SkuGenerateIn,
    SkuGenerateOut,
)
from app.pms.sku_coding.models.sku_coding import (
    SkuCodeTerm,
    SkuCodeTermGroup,
)
from app.pms.sku_coding.services.sku_coding_service import SkuCodingService

router = APIRouter(prefix="/pms/sku-coding", tags=["pms-sku-coding"])


def _problem_400(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail=message)


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail=message)


@router.get("/term-groups", response_model=ListOut[SkuCodeTermGroupOut])
def list_term_groups(
    product_kind: str | None = Query(None),
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    stmt = select(SkuCodeTermGroup).order_by(
        SkuCodeTermGroup.product_kind.asc(),
        SkuCodeTermGroup.sort_order.asc(),
        SkuCodeTermGroup.group_code.asc(),
    )
    if product_kind:
        stmt = stmt.where(SkuCodeTermGroup.product_kind == product_kind.strip().upper())
    if active_only:
        stmt = stmt.where(SkuCodeTermGroup.is_active.is_(True))
    return {"ok": True, "data": list(db.execute(stmt).scalars().all())}


@router.get("/terms", response_model=ListOut[SkuCodeTermOut])
def list_terms(
    group_id: int | None = Query(None, ge=1),
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    stmt = select(SkuCodeTerm).order_by(SkuCodeTerm.group_id.asc(), SkuCodeTerm.sort_order.asc(), SkuCodeTerm.code.asc())
    if group_id is not None:
        stmt = stmt.where(SkuCodeTerm.group_id == int(group_id))
    if active_only:
        stmt = stmt.where(SkuCodeTerm.is_active.is_(True))
    return {"ok": True, "data": list(db.execute(stmt).scalars().all())}


@router.post("/terms", response_model=SkuCodeTermOut, status_code=status.HTTP_201_CREATED)
def create_term(payload: SkuCodeTermCreate, db: Session = Depends(get_db)):
    group = db.get(SkuCodeTermGroup, int(payload.group_id))
    if group is None or not bool(group.is_active):
        raise _problem_400("字典分组不存在或已停用")
    obj = SkuCodeTerm(
        group_id=int(payload.group_id),
        name_cn=payload.name_cn,
        code=payload.code.upper(),
        sort_order=int(payload.sort_order),
        remark=payload.remark,
    )
    db.add(obj)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise _problem_400(f"字典项写入失败：{str(e)}") from e
    db.refresh(obj)
    return obj


@router.patch("/terms/{term_id}", response_model=SkuCodeTermOut)
def update_term(term_id: int, payload: SkuCodeTermUpdate, db: Session = Depends(get_db)):
    obj = db.get(SkuCodeTerm, int(term_id))
    if obj is None:
        raise _not_found("字典项不存在")
    data = payload.model_dump(exclude_unset=True)
    if "code" in data and obj.is_locked:
        raise HTTPException(status_code=409, detail="字典项编码已锁定，不能修改 code")
    for k, v in data.items():
        if k == "code" and v is not None:
            v = str(v).upper()
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/terms/{term_id}/enable", response_model=SkuCodeTermOut)
def enable_term(term_id: int, db: Session = Depends(get_db)):
    obj = db.get(SkuCodeTerm, int(term_id))
    if obj is None:
        raise _not_found("字典项不存在")
    obj.is_active = True
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/terms/{term_id}/disable", response_model=SkuCodeTermOut)
def disable_term(term_id: int, db: Session = Depends(get_db)):
    obj = db.get(SkuCodeTerm, int(term_id))
    if obj is None:
        raise _not_found("字典项不存在")
    obj.is_active = False
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/generate", response_model=SkuGenerateOut)
def generate_sku(payload: SkuGenerateIn, db: Session = Depends(get_db)):
    try:
        data = SkuCodingService(db).generate(
            product_kind=payload.product_kind,
            brand_id=int(payload.brand_id),
            category_id=int(payload.category_id),
            term_ids=payload.term_ids,
            text_segments=payload.text_segments,
            spec_text=payload.spec_text,
        )
        return {"ok": True, "data": data}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
