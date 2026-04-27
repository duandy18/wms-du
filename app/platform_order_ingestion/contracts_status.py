# Module split: platform order ingestion store-level status API contracts.
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PlatformOrderIngestionStoreOut(BaseModel):
    id: int
    platform: str
    store_code: str
    store_name: str
    active: bool


class PlatformOrderIngestionAppOut(BaseModel):
    configured: bool
    enabled_count: int
    status: str


class PlatformOrderIngestionCredentialOut(BaseModel):
    present: bool
    credential_type: str | None
    credential_status: str
    expires_at: str | None
    expired: bool
    scope: str | None
    granted_identity_type: str | None
    granted_identity_value: str | None
    granted_identity_display: str | None


class PlatformOrderIngestionConnectionOut(BaseModel):
    present: bool
    auth_source: str
    connection_status: str
    credential_status: str
    reauth_required: bool
    pull_ready: bool
    status: str
    status_reason: str | None
    last_authorized_at: str | None
    last_pull_checked_at: str | None
    last_error_at: str | None


class PlatformOrderIngestionLatestRunOut(BaseModel):
    id: int
    status: str
    page: int
    page_size: int
    has_more: bool
    orders_count: int
    success_count: int
    failed_count: int
    started_at: str | None
    finished_at: str | None
    error_message: str | None


class PlatformOrderIngestionLatestJobOut(BaseModel):
    id: int
    job_type: str
    status: str
    time_from: str | None
    time_to: str | None
    order_status: int | None
    page_size: int
    cursor_page: int
    last_run_at: str | None
    last_success_at: str | None
    last_error_at: str | None
    last_error_message: str | None
    created_at: str | None
    latest_run: PlatformOrderIngestionLatestRunOut | None = None


class PlatformOrderIngestionStoreStatusDataOut(BaseModel):
    platform: str
    store: PlatformOrderIngestionStoreOut
    app: PlatformOrderIngestionAppOut
    credential: PlatformOrderIngestionCredentialOut
    connection: PlatformOrderIngestionConnectionOut
    latest_job: PlatformOrderIngestionLatestJobOut | None
    pull_ready: bool
    blocked_reasons: list[str]
    meta: dict[str, Any] | None = None


class PlatformOrderIngestionStoreStatusEnvelopeOut(BaseModel):
    ok: bool
    data: PlatformOrderIngestionStoreStatusDataOut
