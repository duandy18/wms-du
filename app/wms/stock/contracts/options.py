from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Base(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


class InventoryOptionsQuery(_Base):
    item_q: Optional[str] = Field(default=None, description="商品编码/名称模糊搜索")
    item_limit: Annotated[int, Field(ge=1, le=500)] = 200
    warehouses_active_only: bool = True

    @field_validator("item_q", mode="before")
    @classmethod
    def _trim_item_q(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v


class InventoryWarehouseOption(_Base):
    id: Annotated[int, Field(ge=1)]
    name: str
    code: Optional[str] = None
    active: bool


class InventoryItemOption(_Base):
    id: Annotated[int, Field(ge=1)]
    sku: str
    name: str


class InventoryOptionsResponse(_Base):
    warehouses: list[InventoryWarehouseOption] = Field(default_factory=list)
    items: list[InventoryItemOption] = Field(default_factory=list)


__all__ = [
    "InventoryOptionsQuery",
    "InventoryWarehouseOption",
    "InventoryItemOption",
    "InventoryOptionsResponse",
]
