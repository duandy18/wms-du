from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ModuleGroupProvinceOut(BaseModel):
    id: int
    group_id: int
    province_code: Optional[str] = None
    province_name: Optional[str] = None


class ModuleGroupProvinceWriteIn(BaseModel):
    province_code: Optional[str] = Field(default=None, max_length=32)
    province_name: Optional[str] = Field(default=None, max_length=64)


class ModuleGroupOut(BaseModel):
    id: int
    template_id: int
    name: str
    sort_order: int
    active: bool
    provinces: list[ModuleGroupProvinceOut]


class ModuleGroupsOut(BaseModel):
    ok: bool = True
    groups: list[ModuleGroupOut]


class ModuleGroupSingleOut(BaseModel):
    ok: bool = True
    group: ModuleGroupOut


class ModuleGroupDeleteOut(BaseModel):
    ok: bool = True
    deleted_group_id: int


class ModuleGroupWriteIn(BaseModel):
    sort_order: Optional[int] = Field(default=None, ge=0)
    active: bool = True
    provinces: list[ModuleGroupProvinceWriteIn] = Field(default_factory=list)
