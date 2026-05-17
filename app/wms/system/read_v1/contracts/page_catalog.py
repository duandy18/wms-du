# app/wms/system/read_v1/contracts/page_catalog.py
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WmsSystemPageCatalogPageOut(_Base):
    page_code: str = Field(..., min_length=1, max_length=64)
    page_name: str = Field(..., min_length=1, max_length=64)
    route_path: str | None = Field(default=None, max_length=255)
    parent_page_code: str | None = Field(default=None, max_length=64)
    level: int = Field(..., ge=1, le=3)
    read_permission_code: str | None = Field(default=None, max_length=128)
    write_permission_code: str | None = Field(default=None, max_length=128)
    is_active: bool
    sort_order: int
    source_updated_at: datetime | None = None


class WmsSystemPageCatalogOut(_Base):
    app_code: Literal["wms"]
    app_name: str = Field(..., min_length=1)
    pages: list[WmsSystemPageCatalogPageOut] = Field(default_factory=list)


__all__ = [
    "WmsSystemPageCatalogOut",
    "WmsSystemPageCatalogPageOut",
]
