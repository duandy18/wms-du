# Module split: platform order ingestion unified mock API contracts.
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


PlatformMockPlatform = Literal["pdd", "jd", "taobao"]
PlatformMockScenario = Literal["normal", "address_missing", "item_abnormal", "combo", "mixed"]


class PlatformOrderIngestionMockAuthorizeRequest(BaseModel):
    platform: PlatformMockPlatform = Field(..., description="平台：pdd / jd / taobao")
    granted_identity_display: str | None = Field(default=None)
    access_token: str | None = Field(default=None)
    refresh_token: str | None = Field(default=None)
    expires_in_days: int = Field(default=365, ge=1, le=3650)
    pull_ready: bool = Field(default=True)

    @field_validator("platform", mode="before")
    @classmethod
    def _lower_platform(cls, value: str) -> str:
        return str(value or "").strip().lower()


class PlatformOrderIngestionMockIngestOrdersRequest(BaseModel):
    platform: PlatformMockPlatform = Field(..., description="平台：pdd / jd / taobao")
    scenario: PlatformMockScenario = Field(default="mixed")
    count: int = Field(default=6, ge=1, le=100)

    @field_validator("platform", mode="before")
    @classmethod
    def _lower_platform(cls, value: str) -> str:
        return str(value or "").strip().lower()


class PlatformOrderIngestionMockClearOrdersRequest(BaseModel):
    platform: PlatformMockPlatform = Field(..., description="平台：pdd / jd / taobao")
    clear_connection: bool = Field(default=False)
    clear_credential: bool = Field(default=False)

    @field_validator("platform", mode="before")
    @classmethod
    def _lower_platform(cls, value: str) -> str:
        return str(value or "").strip().lower()
