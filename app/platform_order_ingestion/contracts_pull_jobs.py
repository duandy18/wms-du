# Module split: platform order ingestion pull-job API contracts.
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


PlatformOrderPullPlatform = Literal["pdd", "taobao", "jd"]
PlatformOrderPullJobType = Literal["manual", "scheduled", "repair"]
PlatformOrderPullJobStatus = Literal["pending", "running", "success", "partial_success", "failed", "cancelled"]
PlatformOrderPullRunStatus = Literal["running", "success", "partial_success", "failed"]
PlatformOrderPullLogLevel = Literal["info", "warn", "error"]


def _normalize_datetime(value: datetime | str | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return None

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass

    try:
        normalized = text.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("datetime must be yyyy-MM-dd HH:mm:ss or ISO-8601") from exc


class PlatformOrderPullJobCreateIn(BaseModel):
    platform: PlatformOrderPullPlatform = Field(..., description="平台：pdd / taobao / jd")
    store_id: int = Field(..., gt=0)
    job_type: PlatformOrderPullJobType = "manual"
    time_from: datetime | None = None
    time_to: datetime | None = None
    order_status: int | None = Field(default=None, gt=0)
    page_size: int = Field(default=50, gt=0, le=100)
    request_payload: dict[str, Any] | None = None

    @field_validator("time_from", "time_to", mode="before")
    @classmethod
    def _parse_dt(cls, value: datetime | str | None) -> datetime | None:
        return _normalize_datetime(value)

    @field_validator("platform", mode="before")
    @classmethod
    def _lower_platform(cls, value: str) -> str:
        return str(value or "").strip().lower()

    @field_validator("job_type", mode="before")
    @classmethod
    def _lower_job_type(cls, value: str) -> str:
        return str(value or "").strip().lower()


class PlatformOrderPullJobRunCreateIn(BaseModel):
    page: int | None = Field(default=None, gt=0)


class PlatformOrderPullJobOut(BaseModel):
    id: int
    platform: str
    store_id: int
    job_type: str
    status: str
    time_from: str | None
    time_to: str | None
    order_status: int | None
    page_size: int
    cursor_page: int
    request_payload: dict[str, Any] | None
    created_by: int | None
    last_run_at: str | None
    last_success_at: str | None
    last_error_at: str | None
    last_error_message: str | None
    created_at: str | None
    updated_at: str | None


class PlatformOrderPullJobRunOut(BaseModel):
    id: int
    job_id: int
    platform: str
    store_id: int
    status: str
    page: int
    page_size: int
    has_more: bool
    started_at: str | None
    finished_at: str | None
    orders_count: int
    success_count: int
    failed_count: int
    request_payload: dict[str, Any] | None
    result_payload: dict[str, Any] | None
    error_message: str | None
    created_at: str | None


class PlatformOrderPullJobRunLogOut(BaseModel):
    id: int
    job_id: int
    run_id: int
    level: str
    event_type: str
    platform_order_no: str | None
    native_order_id: int | None
    message: str | None
    payload: dict[str, Any] | None
    created_at: str | None


class PlatformOrderPullJobListDataOut(BaseModel):
    rows: list[PlatformOrderPullJobOut]
    total: int
    limit: int
    offset: int


class PlatformOrderPullJobDetailDataOut(BaseModel):
    job: PlatformOrderPullJobOut
    runs: list[PlatformOrderPullJobRunOut]
    logs: list[PlatformOrderPullJobRunLogOut]


class PlatformOrderPullJobRunDataOut(BaseModel):
    job: PlatformOrderPullJobOut
    run: PlatformOrderPullJobRunOut
    logs: list[PlatformOrderPullJobRunLogOut]


class PlatformOrderPullJobEnvelopeOut(BaseModel):
    ok: bool
    data: PlatformOrderPullJobOut


class PlatformOrderPullJobListEnvelopeOut(BaseModel):
    ok: bool
    data: PlatformOrderPullJobListDataOut


class PlatformOrderPullJobDetailEnvelopeOut(BaseModel):
    ok: bool
    data: PlatformOrderPullJobDetailDataOut


class PlatformOrderPullJobRunEnvelopeOut(BaseModel):
    ok: bool
    data: PlatformOrderPullJobRunDataOut
