# app/pms/projections/contracts/pms_projection.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ProjectionResource = Literal["items", "suppliers", "uoms", "sku-codes", "barcodes"]
SyncRunStatus = Literal["RUNNING", "SUCCESS", "FAILED"]


class PmsProjectionSyncRunOut(BaseModel):
    id: int
    resource: str
    status: SyncRunStatus
    fetched: int = 0
    upserted: int = 0
    pages: int = 0
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None
    error_message: str | None = None
    triggered_by_user_id: int | None = None
    pms_api_base_url_snapshot: str | None = None
    sync_version: str | None = None


class PmsProjectionResourceStatusOut(BaseModel):
    resource: ProjectionResource
    table_name: str
    row_count: int
    max_synced_at: datetime | None = None
    last_sync_run: PmsProjectionSyncRunOut | None = None


class PmsProjectionStatusOut(BaseModel):
    pms_api_base_url_configured: bool
    resources: list[PmsProjectionResourceStatusOut] = Field(default_factory=list)


class PmsProjectionListOut(BaseModel):
    resource: ProjectionResource
    table_name: str
    limit: int
    offset: int
    total: int
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)


class PmsProjectionSyncOut(BaseModel):
    run: PmsProjectionSyncRunOut


class PmsProjectionCheckIssueOut(BaseModel):
    issue_type: str
    resource: ProjectionResource
    source_id: str
    message: str
    item_id: int | None = None
    item_uom_id: int | None = None
    supplier_id: int | None = None
    projection_item_id: int | None = None


class PmsProjectionCheckOut(BaseModel):
    resource: ProjectionResource
    ok: bool
    issue_count: int
    issues: list[PmsProjectionCheckIssueOut] = Field(default_factory=list)


class PmsProjectionSyncRunsOut(BaseModel):
    resource: ProjectionResource | None = None
    limit: int
    runs: list[PmsProjectionSyncRunOut] = Field(default_factory=list)


__all__ = [
    "PmsProjectionCheckIssueOut",
    "PmsProjectionCheckOut",
    "PmsProjectionListOut",
    "PmsProjectionResourceStatusOut",
    "PmsProjectionStatusOut",
    "PmsProjectionSyncOut",
    "PmsProjectionSyncRunOut",
    "PmsProjectionSyncRunsOut",
    "ProjectionResource",
    "SyncRunStatus",
]
