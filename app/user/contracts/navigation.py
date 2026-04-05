# app/user/contracts/navigation.py
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


class NavigationPageOut(_Base):
    code: Annotated[str, Field(min_length=1, max_length=64)]
    name: Annotated[str, Field(min_length=1, max_length=64)]

    parent_code: Annotated[str | None, Field(default=None, max_length=64)] = None
    level: int
    domain_code: Annotated[str, Field(min_length=1, max_length=32)]

    show_in_topbar: bool
    show_in_sidebar: bool
    sort_order: int
    is_active: bool
    inherit_permissions: bool

    effective_read_permission: Annotated[str | None, Field(default=None, max_length=128)] = None
    effective_write_permission: Annotated[str | None, Field(default=None, max_length=128)] = None

    children: list["NavigationPageOut"] = Field(default_factory=list)


class NavigationRoutePrefixOut(_Base):
    route_prefix: Annotated[str, Field(min_length=1, max_length=255)]
    page_code: Annotated[str, Field(min_length=1, max_length=64)]
    sort_order: int
    is_active: bool

    effective_read_permission: Annotated[str | None, Field(default=None, max_length=128)] = None
    effective_write_permission: Annotated[str | None, Field(default=None, max_length=128)] = None


class MyNavigationOut(_Base):
    pages: list[NavigationPageOut] = Field(default_factory=list)
    route_prefixes: list[NavigationRoutePrefixOut] = Field(default_factory=list)


NavigationPageOut.model_rebuild()

__all__ = [
    "NavigationPageOut",
    "NavigationRoutePrefixOut",
    "MyNavigationOut",
]
