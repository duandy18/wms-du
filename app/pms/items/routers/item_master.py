# app/pms/items/routers/item_master.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.pms.items.contracts.item_master import (
    ItemAttributeDefCreate,
    ItemAttributeDefOut,
    ItemAttributeDefUpdate,
    ItemAttributeOptionCreate,
    ItemAttributeOptionOut,
    ItemAttributeOptionUpdate,
    ItemAttributeValuesReplaceIn,
    ItemAttributeValueOut,
    ListOut,
    PmsBrandCreate,
    PmsBrandOut,
    PmsBrandUpdate,
    PmsCategoryCreate,
    PmsCategoryOut,
    PmsCategoryUpdate,
)
from app.pms.items.models.item import Item
from app.pms.items.models.item_master import (
    ItemAttributeDef,
    ItemAttributeOption,
    ItemAttributeValue,
    PmsBrand,
    PmsBusinessCategory,
)


router = APIRouter(tags=["pms-master-data"])


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


def _build_path_code(db: Session, *, parent_id: int | None, category_code: str) -> str:
    code = category_code.strip().upper()
    if parent_id is None:
        return code
    parent = db.get(PmsBusinessCategory, int(parent_id))
    if parent is None:
        raise ValueError("父级分类不存在")
    return f"{parent.path_code}.{code}"


@router.get("/pms/brands", response_model=ListOut[PmsBrandOut])
def list_pms_brands(active_only: bool = Query(False), db: Session = Depends(get_db)):
    stmt = select(PmsBrand).order_by(PmsBrand.sort_order.asc(), PmsBrand.code.asc(), PmsBrand.id.asc())
    if active_only:
        stmt = stmt.where(PmsBrand.is_active.is_(True))
    return {"ok": True, "data": list(db.execute(stmt).scalars().all())}


@router.post("/pms/brands", response_model=PmsBrandOut, status_code=status.HTTP_201_CREATED)
def create_pms_brand(payload: PmsBrandCreate, db: Session = Depends(get_db)):
    obj = PmsBrand(
        name_cn=payload.name_cn,
        code=payload.code.upper(),
        sort_order=int(payload.sort_order),
        remark=payload.remark,
    )
    db.add(obj)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise _bad_request(f"品牌写入失败：{getattr(e, 'orig', e)}") from e
    db.refresh(obj)
    return obj


@router.patch("/pms/brands/{brand_id}", response_model=PmsBrandOut)
def update_pms_brand(brand_id: int, payload: PmsBrandUpdate, db: Session = Depends(get_db)):
    obj = db.get(PmsBrand, int(brand_id))
    if obj is None:
        raise _not_found("品牌不存在")
    data = payload.model_dump(exclude_unset=True)
    if "code" in data and obj.is_locked:
        raise HTTPException(status_code=409, detail="品牌编码已锁定，不能修改 code")
    for k, v in data.items():
        if k == "code" and v is not None:
            v = str(v).upper()
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/pms/brands/{brand_id}/enable", response_model=PmsBrandOut)
def enable_pms_brand(brand_id: int, db: Session = Depends(get_db)):
    obj = db.get(PmsBrand, int(brand_id))
    if obj is None:
        raise _not_found("品牌不存在")
    obj.is_active = True
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/pms/brands/{brand_id}/disable", response_model=PmsBrandOut)
def disable_pms_brand(brand_id: int, db: Session = Depends(get_db)):
    obj = db.get(PmsBrand, int(brand_id))
    if obj is None:
        raise _not_found("品牌不存在")
    obj.is_active = False
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/pms/brands/{brand_id}/lock", response_model=PmsBrandOut)
def lock_pms_brand(brand_id: int, db: Session = Depends(get_db)):
    obj = db.get(PmsBrand, int(brand_id))
    if obj is None:
        raise _not_found("品牌不存在")
    obj.is_locked = True
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/pms/brands/{brand_id}/unlock", response_model=PmsBrandOut)
def unlock_pms_brand(brand_id: int, db: Session = Depends(get_db)):
    obj = db.get(PmsBrand, int(brand_id))
    if obj is None:
        raise _not_found("品牌不存在")
    obj.is_locked = False
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/pms/categories", response_model=ListOut[PmsCategoryOut])
def list_pms_categories(
    product_kind: str | None = Query(None),
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    stmt = select(PmsBusinessCategory).order_by(
        PmsBusinessCategory.level.asc(),
        PmsBusinessCategory.sort_order.asc(),
        PmsBusinessCategory.path_code.asc(),
    )
    if product_kind:
        stmt = stmt.where(PmsBusinessCategory.product_kind == product_kind.strip().upper())
    if active_only:
        stmt = stmt.where(PmsBusinessCategory.is_active.is_(True))
    return {"ok": True, "data": list(db.execute(stmt).scalars().all())}


@router.post("/pms/categories", response_model=PmsCategoryOut, status_code=status.HTTP_201_CREATED)
def create_pms_category(payload: PmsCategoryCreate, db: Session = Depends(get_db)):
    try:
        path_code = _build_path_code(db, parent_id=payload.parent_id, category_code=payload.category_code)
    except ValueError as e:
        raise _bad_request(str(e)) from e

    obj = PmsBusinessCategory(
        parent_id=payload.parent_id,
        level=int(payload.level),
        product_kind=payload.product_kind,
        category_name=payload.category_name,
        category_code=payload.category_code.upper(),
        path_code=path_code,
        is_leaf=bool(payload.is_leaf),
        sort_order=int(payload.sort_order),
        remark=payload.remark,
    )
    db.add(obj)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise _bad_request(f"内部分类写入失败：{getattr(e, 'orig', e)}") from e
    db.refresh(obj)
    return obj


@router.patch("/pms/categories/{category_id}", response_model=PmsCategoryOut)
def update_pms_category(category_id: int, payload: PmsCategoryUpdate, db: Session = Depends(get_db)):
    obj = db.get(PmsBusinessCategory, int(category_id))
    if obj is None:
        raise _not_found("内部分类不存在")
    data = payload.model_dump(exclude_unset=True)
    if "category_code" in data and obj.is_locked:
        raise HTTPException(status_code=409, detail="内部分类编码已锁定，不能修改 category_code")
    for k, v in data.items():
        if k == "category_code" and v is not None:
            v = str(v).upper()
        setattr(obj, k, v)
    if "category_code" in data:
        obj.path_code = _build_path_code(db, parent_id=obj.parent_id, category_code=obj.category_code)
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/pms/categories/{category_id}/enable", response_model=PmsCategoryOut)
def enable_pms_category(category_id: int, db: Session = Depends(get_db)):
    obj = db.get(PmsBusinessCategory, int(category_id))
    if obj is None:
        raise _not_found("内部分类不存在")
    obj.is_active = True
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/pms/categories/{category_id}/disable", response_model=PmsCategoryOut)
def disable_pms_category(category_id: int, db: Session = Depends(get_db)):
    obj = db.get(PmsBusinessCategory, int(category_id))
    if obj is None:
        raise _not_found("内部分类不存在")
    obj.is_active = False
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/pms/categories/{category_id}/lock", response_model=PmsCategoryOut)
def lock_pms_category(category_id: int, db: Session = Depends(get_db)):
    obj = db.get(PmsBusinessCategory, int(category_id))
    if obj is None:
        raise _not_found("内部分类不存在")
    obj.is_locked = True
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/pms/categories/{category_id}/unlock", response_model=PmsCategoryOut)
def unlock_pms_category(category_id: int, db: Session = Depends(get_db)):
    obj = db.get(PmsBusinessCategory, int(category_id))
    if obj is None:
        raise _not_found("内部分类不存在")
    obj.is_locked = False
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/pms/item-attribute-defs", response_model=ListOut[ItemAttributeDefOut])
def list_item_attribute_defs(
    product_kind: str | None = Query(None),
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    stmt = select(ItemAttributeDef).order_by(
        ItemAttributeDef.product_kind.asc(),
        ItemAttributeDef.sort_order.asc(),
        ItemAttributeDef.code.asc(),
    )
    if product_kind:
        stmt = stmt.where(ItemAttributeDef.product_kind == product_kind.strip().upper())
    if active_only:
        stmt = stmt.where(ItemAttributeDef.is_active.is_(True))
    return {"ok": True, "data": list(db.execute(stmt).scalars().all())}


@router.post("/pms/item-attribute-defs", response_model=ItemAttributeDefOut, status_code=status.HTTP_201_CREATED)
def create_item_attribute_def(payload: ItemAttributeDefCreate, db: Session = Depends(get_db)):
    obj = ItemAttributeDef(
        code=payload.code.upper(),
        name_cn=payload.name_cn,
        name_en=payload.name_en,
        product_kind=payload.product_kind,
        value_type=payload.value_type,
        selection_mode=payload.selection_mode,
        unit=payload.unit,
        is_item_required=bool(payload.is_item_required),
        is_sku_required=bool(payload.is_sku_required),
        is_sku_segment=bool(payload.is_sku_segment),
        sort_order=int(payload.sort_order),
        remark=payload.remark,
    )
    db.add(obj)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise _bad_request(f"属性模板写入失败：{getattr(e, 'orig', e)}") from e
    db.refresh(obj)
    return obj


@router.patch("/pms/item-attribute-defs/{attribute_def_id}", response_model=ItemAttributeDefOut)
def update_item_attribute_def(attribute_def_id: int, payload: ItemAttributeDefUpdate, db: Session = Depends(get_db)):
    obj = db.get(ItemAttributeDef, int(attribute_def_id))
    if obj is None:
        raise _not_found("属性模板不存在")
    data = payload.model_dump(exclude_unset=True)
    if "selection_mode" in data and obj.is_locked:
        raise HTTPException(status_code=409, detail="属性模板已锁定，不能修改 selection_mode")
    if "selection_mode" in data and obj.value_type != "OPTION" and data["selection_mode"] != "SINGLE":
        raise _bad_request("非 OPTION 属性只允许 selection_mode=SINGLE")
    for k, v in data.items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/pms/item-attribute-defs/{attribute_def_id}/enable", response_model=ItemAttributeDefOut)
def enable_item_attribute_def(attribute_def_id: int, db: Session = Depends(get_db)):
    obj = db.get(ItemAttributeDef, int(attribute_def_id))
    if obj is None:
        raise _not_found("属性模板不存在")
    obj.is_active = True
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/pms/item-attribute-defs/{attribute_def_id}/disable", response_model=ItemAttributeDefOut)
def disable_item_attribute_def(attribute_def_id: int, db: Session = Depends(get_db)):
    obj = db.get(ItemAttributeDef, int(attribute_def_id))
    if obj is None:
        raise _not_found("属性模板不存在")
    obj.is_active = False
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/pms/item-attribute-defs/{attribute_def_id}/lock", response_model=ItemAttributeDefOut)
def lock_item_attribute_def(attribute_def_id: int, db: Session = Depends(get_db)):
    obj = db.get(ItemAttributeDef, int(attribute_def_id))
    if obj is None:
        raise _not_found("属性模板不存在")
    obj.is_locked = True
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/pms/item-attribute-defs/{attribute_def_id}/unlock", response_model=ItemAttributeDefOut)
def unlock_item_attribute_def(attribute_def_id: int, db: Session = Depends(get_db)):
    obj = db.get(ItemAttributeDef, int(attribute_def_id))
    if obj is None:
        raise _not_found("属性模板不存在")
    obj.is_locked = False
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/pms/item-attribute-defs/{attribute_def_id}/options", response_model=ListOut[ItemAttributeOptionOut])
def list_item_attribute_options(attribute_def_id: int, active_only: bool = Query(False), db: Session = Depends(get_db)):
    stmt = (
        select(ItemAttributeOption)
        .where(ItemAttributeOption.attribute_def_id == int(attribute_def_id))
        .order_by(ItemAttributeOption.sort_order.asc(), ItemAttributeOption.option_code.asc())
    )
    if active_only:
        stmt = stmt.where(ItemAttributeOption.is_active.is_(True))
    return {"ok": True, "data": list(db.execute(stmt).scalars().all())}


@router.post(
    "/pms/item-attribute-defs/{attribute_def_id}/options",
    response_model=ItemAttributeOptionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_item_attribute_option(
    attribute_def_id: int,
    payload: ItemAttributeOptionCreate,
    db: Session = Depends(get_db),
):
    attr = db.get(ItemAttributeDef, int(attribute_def_id))
    if attr is None:
        raise _not_found("属性模板不存在")
    if attr.value_type != "OPTION":
        raise _bad_request("只有 OPTION 类型属性允许维护选项")

    obj = ItemAttributeOption(
        attribute_def_id=int(attribute_def_id),
        option_code=payload.option_code.upper(),
        option_name=payload.option_name,
        sort_order=int(payload.sort_order),
    )
    db.add(obj)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise _bad_request(f"属性选项写入失败：{getattr(e, 'orig', e)}") from e
    db.refresh(obj)
    return obj


@router.patch("/pms/item-attribute-options/{option_id}", response_model=ItemAttributeOptionOut)
def update_item_attribute_option(option_id: int, payload: ItemAttributeOptionUpdate, db: Session = Depends(get_db)):
    obj = db.get(ItemAttributeOption, int(option_id))
    if obj is None:
        raise _not_found("属性选项不存在")
    data = payload.model_dump(exclude_unset=True)
    if obj.is_locked and data:
        raise HTTPException(status_code=409, detail="属性选项已锁定，不能修改 option_name 或 sort_order")
    for k, v in data.items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/pms/item-attribute-options/{option_id}/lock", response_model=ItemAttributeOptionOut)
def lock_item_attribute_option(option_id: int, db: Session = Depends(get_db)):
    obj = db.get(ItemAttributeOption, int(option_id))
    if obj is None:
        raise _not_found("属性选项不存在")
    obj.is_locked = True
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/pms/item-attribute-options/{option_id}/unlock", response_model=ItemAttributeOptionOut)
def unlock_item_attribute_option(option_id: int, db: Session = Depends(get_db)):
    obj = db.get(ItemAttributeOption, int(option_id))
    if obj is None:
        raise _not_found("属性选项不存在")
    obj.is_locked = False
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/pms/item-attribute-options/{option_id}/enable", response_model=ItemAttributeOptionOut)
def enable_item_attribute_option(option_id: int, db: Session = Depends(get_db)):
    obj = db.get(ItemAttributeOption, int(option_id))
    if obj is None:
        raise _not_found("属性选项不存在")
    obj.is_active = True
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/pms/item-attribute-options/{option_id}/disable", response_model=ItemAttributeOptionOut)
def disable_item_attribute_option(option_id: int, db: Session = Depends(get_db)):
    obj = db.get(ItemAttributeOption, int(option_id))
    if obj is None:
        raise _not_found("属性选项不存在")
    obj.is_active = False
    db.commit()
    db.refresh(obj)
    return obj


def _list_item_attribute_value_out(db: Session, item_id: int) -> list[ItemAttributeValueOut]:
    rows = (
        db.execute(
            select(ItemAttributeValue)
            .where(ItemAttributeValue.item_id == int(item_id))
            .order_by(
                ItemAttributeValue.attribute_def_id.asc(),
                ItemAttributeValue.value_option_id.asc().nullsfirst(),
                ItemAttributeValue.id.asc(),
            )
        )
        .scalars()
        .all()
    )

    grouped: dict[int, dict] = {}

    for row in rows:
        key = int(row.attribute_def_id)
        current = grouped.get(key)
        if current is None:
            current = {
                "id": int(row.id),
                "item_id": int(row.item_id),
                "attribute_def_id": key,
                "value_text": row.value_text,
                "value_number": float(row.value_number) if row.value_number is not None else None,
                "value_bool": row.value_bool,
                "value_option_ids": [],
                "value_option_code_snapshots": [],
                "value_unit_snapshot": row.value_unit_snapshot,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            grouped[key] = current

        if row.value_option_id is not None:
            current["value_option_ids"].append(int(row.value_option_id))
            if row.value_option_code_snapshot:
                current["value_option_code_snapshots"].append(str(row.value_option_code_snapshot))

    return [ItemAttributeValueOut.model_validate(x) for x in grouped.values()]


@router.get("/items/{item_id}/attributes", response_model=ListOut[ItemAttributeValueOut])
def list_item_attribute_values(item_id: int, db: Session = Depends(get_db)):
    return {"ok": True, "data": _list_item_attribute_value_out(db, int(item_id))}


@router.put("/items/{item_id}/attributes", response_model=ListOut[ItemAttributeValueOut])
def replace_item_attribute_values(
    item_id: int,
    payload: ItemAttributeValuesReplaceIn,
    db: Session = Depends(get_db),
):
    item = db.get(Item, int(item_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    seen_defs: set[int] = set()

    db.query(ItemAttributeValue).filter(ItemAttributeValue.item_id == int(item_id)).delete()

    for incoming in payload.values:
        attr = db.get(ItemAttributeDef, int(incoming.attribute_def_id))
        if attr is None or not bool(attr.is_active):
            raise _bad_request(f"属性模板不存在或已停用：{incoming.attribute_def_id}")

        attr_id = int(attr.id)
        if attr_id in seen_defs:
            raise _bad_request(f"同一属性不能重复提交：{attr.code}")
        seen_defs.add(attr_id)

        option_ids = incoming.value_option_ids or []

        if attr.value_type == "OPTION":
            if incoming.value_text is not None or incoming.value_number is not None or incoming.value_bool is not None:
                raise _bad_request(f"OPTION 属性只能提交 value_option_ids：{attr.code}")

            if not option_ids:
                raise _bad_request(f"OPTION 属性必须提交 value_option_ids：{attr.code}")

            if attr.selection_mode == "SINGLE" and len(option_ids) > 1:
                raise _bad_request(f"SINGLE 属性最多只能选择一个选项：{attr.code}")

            for option_id in option_ids:
                opt = db.get(ItemAttributeOption, int(option_id))
                if opt is None or int(opt.attribute_def_id) != attr_id or not bool(opt.is_active):
                    raise _bad_request(f"属性选项不存在、已停用或不属于当前属性：{attr.code}")

                db.add(
                    ItemAttributeValue(
                        item_id=int(item_id),
                        attribute_def_id=attr_id,
                        value_text=None,
                        value_number=None,
                        value_bool=None,
                        value_option_id=int(opt.id),
                        value_option_code_snapshot=str(opt.option_code),
                        value_unit_snapshot=attr.unit,
                    )
                )

            continue

        if option_ids:
            raise _bad_request(f"非 OPTION 属性不能提交 value_option_ids：{attr.code}")

        value_text = incoming.value_text
        value_number = incoming.value_number
        value_bool = incoming.value_bool

        if attr.value_type == "TEXT":
            if value_text is None:
                raise _bad_request(f"TEXT 属性必须提交 value_text：{attr.code}")
            value_number = None
            value_bool = None
        elif attr.value_type == "NUMBER":
            if value_number is None:
                raise _bad_request(f"NUMBER 属性必须提交 value_number：{attr.code}")
            value_text = None
            value_bool = None
        elif attr.value_type == "BOOL":
            if value_bool is None:
                raise _bad_request(f"BOOL 属性必须提交 value_bool：{attr.code}")
            value_text = None
            value_number = None
        else:
            raise _bad_request(f"不支持的属性类型：{attr.value_type}")

        db.add(
            ItemAttributeValue(
                item_id=int(item_id),
                attribute_def_id=attr_id,
                value_text=value_text,
                value_number=value_number,
                value_bool=value_bool,
                value_option_id=None,
                value_option_code_snapshot=None,
                value_unit_snapshot=attr.unit,
            )
        )

    db.commit()
    return {"ok": True, "data": _list_item_attribute_value_out(db, int(item_id))}
