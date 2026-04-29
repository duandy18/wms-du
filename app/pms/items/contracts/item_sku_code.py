# app/pms/items/contracts/item_sku_code.py
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ItemSkuCodeType = Literal["PRIMARY", "ALIAS", "LEGACY", "MANUAL"]


def _norm_text(v: object) -> object:
    return v.strip() if isinstance(v, str) else v


class ItemSkuCodeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    code: Annotated[str, Field(min_length=1, max_length=128)]
    code_type: ItemSkuCodeType = "ALIAS"
    is_active: bool = True
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    remark: Annotated[str | None, Field(default=None, max_length=255)] = None

    @field_validator("code", "remark", mode="before")
    @classmethod
    def _trim_text(cls, v: object) -> object:
        return _norm_text(v)

    @model_validator(mode="after")
    def _no_primary_via_create_alias(self) -> "ItemSkuCodeCreate":
        if self.code_type == "PRIMARY":
            raise ValueError("PRIMARY code must be changed via change-primary action")
        return self


class ItemSkuCodeChangePrimary(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    code: Annotated[str, Field(min_length=1, max_length=128)]
    remark: Annotated[str | None, Field(default=None, max_length=255)] = None

    @field_validator("code", "remark", mode="before")
    @classmethod
    def _trim_text(cls, v: object) -> object:
        return _norm_text(v)


class ItemSkuCodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    code: str
    code_type: ItemSkuCodeType
    is_primary: bool
    is_active: bool
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    remark: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
