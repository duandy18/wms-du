# app/api/routers/pricing_integrity_schemas.py
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# ==========================
# Report (Ops Integrity)
# ==========================
class PricingIntegrityArchivedZoneIssue(BaseModel):
    # active=false 但仍占用 province members（最致命：会阻塞新建/修改）
    scheme_id: int
    zone_id: int
    zone_name: str
    zone_active: bool
    province_members: List[str] = Field(default_factory=list)
    province_member_n: int = 0
    suggested_action: str = "ARCHIVE_RELEASE_PROVINCES"


class PricingIntegrityReleasedZoneStillPricedIssue(BaseModel):
    # province members=0 但仍存在报价明细（brackets）—— 幽灵数据，会污染二维表/解释/审计
    scheme_id: int
    zone_id: int
    zone_name: str
    zone_active: bool

    province_member_n: int = 0
    brackets_n: int = 0

    segment_template_id: Optional[int] = None
    suggested_action: str = "DETACH_ZONE_BRACKETS"


class PricingIntegrityArchivedTemplateStillReferencedIssue(BaseModel):
    # template.status=archived 但仍被 zones 引用 —— “以为停用但仍在用”
    scheme_id: int
    template_id: int
    template_name: str
    template_status: str

    referencing_zone_ids: List[int] = Field(default_factory=list)
    referencing_zone_names: List[str] = Field(default_factory=list)
    referencing_zone_n: int = 0

    suggested_action: str = "UNBIND_ARCHIVED_TEMPLATE"


class PricingIntegrityReportSummary(BaseModel):
    blocking: int = 0
    warning: int = 0


class PricingIntegrityReportOut(BaseModel):
    scheme_id: int
    summary: PricingIntegrityReportSummary

    archived_zones_still_occupying: List[PricingIntegrityArchivedZoneIssue] = Field(default_factory=list)

    # Phase 2:
    released_zones_still_priced: List[PricingIntegrityReleasedZoneStillPricedIssue] = Field(default_factory=list)
    archived_templates_still_referenced: List[
        PricingIntegrityArchivedTemplateStillReferencedIssue
    ] = Field(default_factory=list)


# ==========================
# Fix 1: Archive-Release Provinces
# ==========================
class PricingIntegrityFixArchiveReleaseIn(BaseModel):
    scheme_id: int = Field(..., ge=1)
    zone_ids: List[int] = Field(..., min_length=1)
    dry_run: bool = False


class PricingIntegrityFixArchiveReleaseItemOut(BaseModel):
    zone_id: int
    zone_name: str
    ok: bool

    # dry-run 或执行前后用于解释影响
    would_release_provinces: List[str] = Field(default_factory=list)
    would_release_n: int = 0

    # 执行版：给出执行后的状态摘要
    after_active: bool | None = None
    after_province_member_n: int | None = None

    # 错误信息（逐条返回，不因一条失败拖死全部）
    error: str | None = None


class PricingIntegrityFixArchiveReleaseOut(BaseModel):
    scheme_id: int
    dry_run: bool
    items: List[PricingIntegrityFixArchiveReleaseItemOut] = Field(default_factory=list)


# ==========================
# Fix 2: Detach Zone Brackets (only for released zones)
# ==========================
class PricingIntegrityFixDetachZoneBracketsIn(BaseModel):
    scheme_id: int = Field(..., ge=1)
    zone_ids: List[int] = Field(..., min_length=1)
    dry_run: bool = False


class PricingIntegrityFixDetachZoneBracketsItemOut(BaseModel):
    zone_id: int
    zone_name: str
    ok: bool

    province_member_n: int = 0

    would_delete_brackets_n: int = 0
    would_delete_ranges_preview: List[str] = Field(default_factory=list)

    after_brackets_n: int | None = None
    error: str | None = None


class PricingIntegrityFixDetachZoneBracketsOut(BaseModel):
    scheme_id: int
    dry_run: bool
    items: List[PricingIntegrityFixDetachZoneBracketsItemOut] = Field(default_factory=list)


# ==========================
# Fix 3: Unbind Archived Templates (template -> zones.segment_template_id=NULL)
# ==========================
class PricingIntegrityFixUnbindArchivedTemplatesIn(BaseModel):
    scheme_id: int = Field(..., ge=1)
    template_ids: List[int] = Field(..., min_length=1)
    dry_run: bool = False


class PricingIntegrityFixUnbindArchivedTemplatesItemOut(BaseModel):
    template_id: int
    template_name: str
    ok: bool

    template_status: str | None = None

    would_unbind_zone_ids: List[int] = Field(default_factory=list)
    would_unbind_zone_names: List[str] = Field(default_factory=list)
    would_unbind_zone_n: int = 0

    after_unbound_zone_n: int | None = None
    error: str | None = None


class PricingIntegrityFixUnbindArchivedTemplatesOut(BaseModel):
    scheme_id: int
    dry_run: bool
    items: List[PricingIntegrityFixUnbindArchivedTemplatesItemOut] = Field(default_factory=list)
