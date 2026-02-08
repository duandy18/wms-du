# app/api/schemas/platform_sku_mirror_sync.py
from __future__ import annotations

from pydantic import BaseModel, Field


class PlatformSkuMirrorSyncIn(BaseModel):
    platform: str = Field(..., min_length=1, max_length=50)

    # 目标 sku 列表（最小实现：必须显式传入；后续可扩展为“全量同步/分页”）
    platform_sku_ids: list[str] = Field(..., min_length=1)

    # source 用于审计：platform-sync / manual / cron 等
    source: str = Field("platform-sync", min_length=1, max_length=50)


class PlatformSkuMirrorSyncOut(BaseModel):
    ok: bool
    fetched: int
    upserted: int


# ---------------------------------------------------------------------------
# Compat: some routers use "Upsert" naming. Keep them as aliases to avoid
# import/runtime breakage while we converge naming across routes.
# ---------------------------------------------------------------------------
PlatformSkuMirrorUpsertIn = PlatformSkuMirrorSyncIn
PlatformSkuMirrorUpsertOut = PlatformSkuMirrorSyncOut
