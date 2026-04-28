from __future__ import annotations

from pydantic import BaseModel, Field


class ImportPlatformOrderMirrorFromCollectorIn(BaseModel):
    collector_order_id: int = Field(..., ge=1)


class ImportPlatformOrderMirrorFromCollectorOut(BaseModel):
    ok: bool = True
    imported: bool = True
    platform: str
    collector_order_id: int
    mirror_id: int


class SyncPlatformOrderMirrorsFromCollectorIn(BaseModel):
    limit: int = Field(50, ge=1, le=1000)
    offset: int = Field(0, ge=0)


class SyncPlatformOrderMirrorItemOut(BaseModel):
    collector_order_id: int
    mirror_id: int
    imported: bool = True


class SyncPlatformOrderMirrorErrorOut(BaseModel):
    collector_order_id: int | None = None
    error_code: str
    message: str


class SyncPlatformOrderMirrorsFromCollectorOut(BaseModel):
    ok: bool = True
    platform: str
    limit: int
    offset: int
    fetched_count: int
    imported_count: int
    failed_count: int
    items: list[SyncPlatformOrderMirrorItemOut] = Field(default_factory=list)
    errors: list[SyncPlatformOrderMirrorErrorOut] = Field(default_factory=list)
