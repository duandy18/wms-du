# app/pms/items/services/item_sku_code_service.py
from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.pms.items.models.item import Item
from app.pms.items.models.item_sku_code import ItemSkuCode
from app.pms.items.repos.item_sku_code_repo import (
    add_sku_code,
    get_active_sku_code_by_code,
    get_primary_sku_code_by_item_id,
    get_sku_code_by_code,
    get_sku_code_by_id,
    list_sku_codes_by_item_id,
)


_SKU_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,127}$")
_NON_PRIMARY_TYPES = {"ALIAS", "LEGACY", "MANUAL"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_sku_code(v: object) -> str:
    s = str(v or "").strip().upper()
    if not s:
        raise ValueError("sku code 不能为空")
    if len(s) > 128:
        raise ValueError("sku code 长度不能超过 128")
    if not _SKU_PATTERN.fullmatch(s):
        raise ValueError("invalid sku code")
    return s


def normalize_sku_code_or_none(v: object) -> str | None:
    s = str(v or "").strip()
    if not s:
        return None
    return normalize_sku_code(s)


def normalize_code_type(v: object) -> str:
    raw = getattr(v, "value", v)
    s = str(raw or "").strip().upper()
    if s not in {"PRIMARY", "ALIAS", "LEGACY", "MANUAL"}:
        raise ValueError("invalid sku code type")
    return s


class ItemSkuCodeService:
    """
    商品 SKU 多编码治理服务。

    边界：
    - item_id 是商品内部身份真相；
    - items.sku 是当前主 SKU 投影；
    - item_sku_codes 是编码治理真相表；
    - 历史单据里的 item_sku / item_sku_snapshot 是当时展示快照，不追改。
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_codes(self, *, item_id: int) -> list[ItemSkuCode]:
        item = self.db.get(Item, int(item_id))
        if item is None:
            raise ValueError("Item not found")
        return list_sku_codes_by_item_id(self.db, item_id=int(item_id))

    def create_primary_code_in_current_tx(
        self,
        *,
        item_id: int,
        code: object,
        effective_from: datetime | None = None,
        remark: str | None = None,
    ) -> ItemSkuCode:
        """
        在当前事务里为新建商品同步 PRIMARY 编码。

        注意：
        - 不 commit，由调用方控制事务；
        - 用于 POST /items 与 POST /items/aggregate；
        - 不能被普通 alias 创建入口调用。
        """
        item = self.db.get(Item, int(item_id))
        if item is None:
            raise ValueError("Item not found")

        code_val = normalize_sku_code(code)
        existing = get_sku_code_by_code(self.db, code=code_val)
        if existing is not None:
            if int(existing.item_id) == int(item_id) and bool(existing.is_primary):
                return existing
            raise ValueError("SKU code duplicate")

        now = utc_now()
        obj = ItemSkuCode(
            item_id=int(item_id),
            code=code_val,
            code_type="PRIMARY",
            is_primary=True,
            is_active=True,
            effective_from=effective_from or now,
            effective_to=None,
            remark=remark,
            created_at=now,
            updated_at=now,
        )
        add_sku_code(self.db, obj)
        self.db.flush()
        return obj

    def create_code(
        self,
        *,
        item_id: int,
        code: object,
        code_type: object = "ALIAS",
        is_active: bool = True,
        effective_from: datetime | None = None,
        effective_to: datetime | None = None,
        remark: str | None = None,
    ) -> ItemSkuCode:
        item = self.db.get(Item, int(item_id))
        if item is None:
            raise ValueError("Item not found")

        code_val = normalize_sku_code(code)
        code_type_val = normalize_code_type(code_type)
        if code_type_val not in _NON_PRIMARY_TYPES:
            raise ValueError("PRIMARY code must be changed via change-primary action")

        existing = get_sku_code_by_code(self.db, code=code_val)
        if existing is not None:
            raise ValueError("SKU code duplicate")

        now = utc_now()
        obj = ItemSkuCode(
            item_id=int(item_id),
            code=code_val,
            code_type=code_type_val,
            is_primary=False,
            is_active=bool(is_active),
            effective_from=effective_from,
            effective_to=effective_to,
            remark=remark,
            created_at=now,
            updated_at=now,
        )
        add_sku_code(self.db, obj)

        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            raise ValueError("SKU code duplicate") from e

        self.db.refresh(obj)
        return obj

    def disable_code(self, *, item_id: int, code_id: int) -> ItemSkuCode:
        obj = get_sku_code_by_id(self.db, code_id=int(code_id))
        if obj is None or int(obj.item_id) != int(item_id):
            raise ValueError("SKU code not found")
        if bool(obj.is_primary):
            raise ValueError("primary sku code cannot be disabled")

        now = utc_now()
        obj.is_active = False
        obj.updated_at = now
        if obj.effective_to is None:
            obj.effective_to = now

        self.db.commit()
        self.db.refresh(obj)
        return obj

    def enable_code(self, *, item_id: int, code_id: int) -> ItemSkuCode:
        obj = get_sku_code_by_id(self.db, code_id=int(code_id))
        if obj is None or int(obj.item_id) != int(item_id):
            raise ValueError("SKU code not found")

        obj.is_active = True
        obj.updated_at = utc_now()

        self.db.commit()
        self.db.refresh(obj)
        return obj

    def change_primary(
        self,
        *,
        item_id: int,
        code: object,
        remark: str | None = None,
    ) -> ItemSkuCode:
        item = self.db.get(Item, int(item_id))
        if item is None:
            raise ValueError("Item not found")

        code_val = normalize_sku_code(code)
        now = utc_now()

        existing = get_sku_code_by_code(self.db, code=code_val)
        if existing is not None and int(existing.item_id) != int(item_id):
            raise ValueError("SKU code duplicate")

        old_primary = get_primary_sku_code_by_item_id(self.db, item_id=int(item_id))

        if old_primary is not None and str(old_primary.code) == code_val:
            old_primary.code_type = "PRIMARY"
            old_primary.is_primary = True
            old_primary.is_active = True
            old_primary.effective_to = None
            old_primary.updated_at = now
            item.sku = code_val
            item.updated_at = now
            self.db.commit()
            self.db.refresh(old_primary)
            return old_primary

        if old_primary is not None:
            old_primary.code_type = "ALIAS"
            old_primary.is_primary = False
            old_primary.is_active = True
            old_primary.effective_to = now
            old_primary.updated_at = now
            self.db.flush()

        if existing is None:
            new_primary = ItemSkuCode(
                item_id=int(item_id),
                code=code_val,
                code_type="PRIMARY",
                is_primary=True,
                is_active=True,
                effective_from=now,
                effective_to=None,
                remark=remark,
                created_at=now,
                updated_at=now,
            )
            add_sku_code(self.db, new_primary)
        else:
            new_primary = existing
            new_primary.code_type = "PRIMARY"
            new_primary.is_primary = True
            new_primary.is_active = True
            new_primary.effective_from = new_primary.effective_from or now
            new_primary.effective_to = None
            new_primary.remark = remark if remark is not None else new_primary.remark
            new_primary.updated_at = now

        item.sku = code_val
        item.updated_at = now

        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            raw = str(getattr(e, "orig", e)).lower()
            if "item_sku_codes" in raw or "items_sku_key" in raw or "unique" in raw:
                raise ValueError("SKU code duplicate") from e
            raise ValueError(f"DB integrity error: {getattr(e, 'orig', e)}") from e

        self.db.refresh(new_primary)
        return new_primary

    def get_item_by_active_code(self, *, code: object) -> Item | None:
        code_val = normalize_sku_code_or_none(code)
        if code_val is None:
            return None
        row = get_active_sku_code_by_code(self.db, code=code_val)
        if row is None:
            return None
        return self.db.get(Item, int(row.item_id))
