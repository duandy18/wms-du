# app/api/schemas/platform_sku_binding.py
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class _StoreCompatMixin(BaseModel):
    """
    ✅ 合同升级：内部治理统一 store_id（stores.id）
    ⚠️ 兼容：保留旧字段名 shop_id（历史误名，语义等同 store_id）

    规则：
    - 入参允许 store_id 或 shop_id 二选一（至少一个）
    - 若只给 store_id，会自动回填 shop_id（兼容旧代码/旧服务逻辑）
    - 若只给 shop_id，会自动回填 store_id（让新前端统一用 store_id）
    """

    store_id: int | None = Field(None, ge=1, description="内部店铺ID（stores.id）")
    shop_id: int | None = Field(None, ge=1, description="兼容旧字段名：语义等同 store_id（stores.id）")

    @model_validator(mode="after")
    def _ensure_store_id(self):
        sid = self.store_id
        hid = self.shop_id
        if sid is None and hid is None:
            raise ValueError("store_id is required")
        if sid is None and hid is not None:
            self.store_id = int(hid)
        if hid is None and sid is not None:
            self.shop_id = int(sid)
        return self


class BindingCreateIn(_StoreCompatMixin):
    platform: str = Field(..., min_length=1, max_length=50)
    platform_sku_id: str = Field(..., min_length=1, max_length=200)

    # ✅ 单入口收敛：仅允许绑定到 FSKU
    # 单品也必须用 single-FSKU 承载（由 FSKU.components 指向 item）
    fsku_id: int = Field(..., ge=1)

    reason: str | None = Field(None, max_length=200)


class BindingUnbindIn(_StoreCompatMixin):
    platform: str = Field(..., min_length=1, max_length=50)
    platform_sku_id: str = Field(..., min_length=1, max_length=200)
    reason: str | None = Field(None, max_length=200)


class BindingRow(_StoreCompatMixin):
    id: int
    platform: str
    platform_sku_id: str

    # 历史兼容：旧数据可能存在 item_id（legacy），读历史时仍可返回
    item_id: int | None
    fsku_id: int | None

    effective_from: datetime
    effective_to: datetime | None
    reason: str | None


class BindingCurrentOut(BaseModel):
    current: BindingRow


class BindingHistoryOut(BaseModel):
    items: list[BindingRow]
    total: int
    limit: int
    offset: int


class BindingMigrateIn(BaseModel):
    # ✅ 单入口收敛：仅允许迁移到 FSKU
    to_fsku_id: int = Field(..., ge=1)
    reason: str | None = Field(None, max_length=200)


class BindingMigrateOut(BaseModel):
    current: BindingRow
