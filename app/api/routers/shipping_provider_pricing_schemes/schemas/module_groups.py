# app/api/routers/shipping_provider_pricing_schemes/schemas/module_groups.py
from __future__ import annotations

from typing import List, Optional, Tuple, Dict

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------
# Out Models
# ---------------------------------------------------------

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
    module_id: int
    module_code: str

    name: str
    sort_order: int
    active: bool

    provinces: List[ModuleGroupProvinceOut] = Field(default_factory=list)


class ModuleGroupsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ok: bool = True
    module_code: str
    groups: List[ModuleGroupOut] = Field(default_factory=list)


# ---------------------------------------------------------
# PUT Input Models
# ---------------------------------------------------------

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


class ModuleGroupPutItemIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, max_length=128)
    sort_order: Optional[int] = Field(None, ge=0)
    active: bool = True

    provinces: List[ModuleGroupProvinceIn] = Field(default_factory=list, min_length=1)

    @field_validator("name")
    @classmethod
    def _trim_name(cls, v: str) -> str:
        t = v.strip()
        if not t:
            raise ValueError("group name must not be empty")
        return t


class ModuleGroupsPutIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    groups: List[ModuleGroupPutItemIn] = Field(default_factory=list, min_length=1)

    # ---------------------------------------------------------
    # module 内 province 不允许跨 group 重复
    # ---------------------------------------------------------

    @model_validator(mode="after")
    def _validate_province_conflicts(self):

        owner: Dict[Tuple[str, str], str] = {}

        for g in self.groups:

            seen = set()

            for p in g.provinces:

                key = (str(p.province_code or ""), str(p.province_name or ""))

                if key in seen:
                    raise ValueError(f"duplicate province inside group '{g.name}'")

                seen.add(key)

                if key in owner and owner[key] != g.name:
                    label = p.province_name or p.province_code or "unknown"
                    raise ValueError(
                        f"province {label} appears in multiple groups "
                        f"('{owner[key]}' and '{g.name}')"
                    )

                owner[key] = g.name

        return self
