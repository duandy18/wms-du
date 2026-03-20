# app/tms/pricing/runtime_policy.py

from __future__ import annotations

from typing import Literal

TemplateRuntimeStatus = Literal[
    "missing",
    "not_active",
    "archived",
    "active",
]

PricingStatus = Literal[
    "provider_disabled",
    "binding_disabled",
    "no_active_template",
    "template_not_active",
    "ready",
]


def compute_template_runtime_status(
    *,
    active_template_id: int | None,
    template_status: str | None,
    template_archived: bool,
) -> TemplateRuntimeStatus:
    if active_template_id is None:
        return "missing"

    status = str(template_status or "").strip().lower()
    if status != "active":
        return "not_active"

    if template_archived:
        return "archived"

    return "active"


def compute_is_template_active(
    *,
    active_template_id: int | None,
    template_status: str | None,
    template_archived: bool,
) -> bool:
    return (
        compute_template_runtime_status(
            active_template_id=active_template_id,
            template_status=template_status,
            template_archived=template_archived,
        )
        == "active"
    )


def compute_pricing_status(
    *,
    provider_active: bool,
    binding_active: bool,
    active_template_id: int | None,
    template_status: str | None,
    template_archived: bool,
) -> PricingStatus:
    if not provider_active:
        return "provider_disabled"

    if not binding_active:
        return "binding_disabled"

    runtime_status = compute_template_runtime_status(
        active_template_id=active_template_id,
        template_status=template_status,
        template_archived=template_archived,
    )

    if runtime_status == "missing":
        return "no_active_template"

    if runtime_status != "active":
        return "template_not_active"

    return "ready"
