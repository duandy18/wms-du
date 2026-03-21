from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

_ALLOWED_TEMPLATE_STATUS = {"draft", "archived"}
_ALLOWED_TEMPLATE_VALIDATION_STATUS = {"not_validated", "passed", "failed"}
_ALLOWED_TEMPLATE_CONFIG_STATUS = {"empty", "incomplete", "ready"}


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shipping_provider_id: int
    shipping_provider_name: str

    name: str
    status: str
    archived_at: Optional[datetime] = None
    validation_status: str

    created_at: datetime
    updated_at: datetime

    used_binding_count: int
    config_status: str
    ranges_count: int
    groups_count: int
    matrix_cells_count: int

    destination_groups: list[dict[str, Any]] = Field(default_factory=list)
    surcharge_configs: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_shape(self):
        if self.status not in _ALLOWED_TEMPLATE_STATUS:
            raise ValueError("status must be one of: draft / archived")

        if self.validation_status not in _ALLOWED_TEMPLATE_VALIDATION_STATUS:
            raise ValueError("validation_status must be one of: not_validated / passed / failed")

        if self.config_status not in _ALLOWED_TEMPLATE_CONFIG_STATUS:
            raise ValueError("config_status must be one of: empty / incomplete / ready")

        return self


class TemplateListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ok: bool = True
    data: list[TemplateOut]


class TemplateDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ok: bool = True
    data: TemplateOut


class TemplateCreateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    shipping_provider_id: int = Field(..., ge=1)
    name: str = Field(..., min_length=1, max_length=128)


class TemplateUpdateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = Field(None, min_length=1, max_length=128)
    status: Optional[str] = Field(None, min_length=1, max_length=16)
    validation_status: Optional[str] = Field(None, min_length=1, max_length=16)

    @model_validator(mode="after")
    def _validate_shape(self):
        if self.status is not None and self.status not in _ALLOWED_TEMPLATE_STATUS:
            raise ValueError("status must be one of: draft / archived")

        if (
            self.validation_status is not None
            and self.validation_status not in _ALLOWED_TEMPLATE_VALIDATION_STATUS
        ):
            raise ValueError("validation_status must be one of: not_validated / passed / failed")

        return self


class TemplateCloneIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
