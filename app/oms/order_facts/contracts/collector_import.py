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
