from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

_ALLOWED_TEMPLATE_STATUS = {"draft", "archived"}
_ALLOWED_TEMPLATE_VALIDATION_STATUS = {"not_validated", "passed", "failed"}
_ALLOWED_TEMPLATE_CONFIG_STATUS = {"empty", "incomplete", "ready"}
_ALLOWED_TEMPLATE_READONLY_REASON = {
    "archived_template",
    "validated_template",
    "cloned_template_structure_locked",
}


class TemplateCapabilitiesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    can_edit_structure: bool
    can_submit_validation: bool
    can_clone: bool
    can_archive: bool
    can_bind: bool
    readonly_reason: Optional[str] = None

    @model_validator(mode="after")
    def _validate_shape(self):
        if (
            self.readonly_reason is not None
            and self.readonly_reason not in _ALLOWED_TEMPLATE_READONLY_REASON
        ):
            raise ValueError(
                "readonly_reason must be one of: archived_template / validated_template / cloned_template_structure_locked"
            )

        return self


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shipping_provider_id: int
    shipping_provider_name: str
    source_template_id: Optional[int] = None

    name: str
    expected_ranges_count: int
    expected_groups_count: int
    expected_matrix_cells_count: int

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

    capabilities: TemplateCapabilitiesOut

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

        if self.expected_ranges_count <= 0:
            raise ValueError("expected_ranges_count must be > 0")

        if self.expected_groups_count <= 0:
            raise ValueError("expected_groups_count must be > 0")

        if self.expected_matrix_cells_count <= 0:
            raise ValueError("expected_matrix_cells_count must be > 0")

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
    expected_ranges_count: int = Field(..., ge=1)
    expected_groups_count: int = Field(..., ge=1)


class TemplateUpdateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = Field(None, min_length=1, max_length=128)
    expected_ranges_count: Optional[int] = Field(None, ge=1)
    expected_groups_count: Optional[int] = Field(None, ge=1)
    status: Optional[str] = Field(None, min_length=1, max_length=16)

    @model_validator(mode="after")
    def _validate_shape(self):
        if self.status is not None and self.status not in _ALLOWED_TEMPLATE_STATUS:
            raise ValueError("status must be one of: draft / archived")

        return self


class TemplateCloneIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
