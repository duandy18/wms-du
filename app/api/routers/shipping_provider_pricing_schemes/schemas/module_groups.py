from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ModuleGroupProvinceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int
    province_code: Optional[str] = None
    province_name: Optional[str] = None


class ModuleGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scheme_id: int

    name: str
    sort_order: int
    active: bool

    provinces: List[ModuleGroupProvinceOut] = Field(default_factory=list)


class ModuleGroupsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ok: bool = True
    groups: List[ModuleGroupOut] = Field(default_factory=list)


class ModuleGroupProvinceIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    province_code: Optional[str] = Field(None, max_length=32)
    province_name: Optional[str] = Field(None, max_length=64)

    @field_validator("province_code", "province_name")
    @classmethod
    def _trim(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        t = v.strip()
        return t or None

    @model_validator(mode="after")
    def _validate(self):
        if not (self.province_code or self.province_name):
            raise ValueError("province_code or province_name must be provided")
        return self


class ModuleGroupWriteIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sort_order: Optional[int] = Field(None, ge=0)
    active: bool = True
    provinces: List[ModuleGroupProvinceIn] = Field(default_factory=list, min_length=1)


class ModuleGroupSingleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ok: bool = True
    group: ModuleGroupOut


class ModuleGroupDeleteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ok: bool = True
    deleted_group_id: int
