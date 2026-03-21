# app/tms/pricing/runtime_policy.py

from __future__ import annotations

from typing import Literal

TemplateRuntimeStatus = Literal[
    "missing",
    "archived",
    "ready",
]

PricingStatus = Literal[
    "provider_disabled",
    "binding_disabled",
    "no_active_template",
    "template_archived",
    "ready",
]


def compute_template_runtime_status(
    *,
    active_template_id: int | None,
    template_archived: bool,
) -> TemplateRuntimeStatus:
    if active_template_id is None:
        return "missing"

    if template_archived:
        return "archived"

    return "ready"


def compute_is_template_active(
    *,
    active_template_id: int | None,
    template_archived: bool,
) -> bool:
    return (
        compute_template_runtime_status(
            active_template_id=active_template_id,
            template_archived=template_archived,
        )
        == "ready"
    )


def compute_pricing_status(
    *,
    provider_active: bool,
    binding_active: bool,
    active_template_id: int | None,
    template_archived: bool,
) -> PricingStatus:
    if not provider_active:
        return "provider_disabled"

    if not binding_active:
        return "binding_disabled"

    runtime_status = compute_template_runtime_status(
        active_template_id=active_template_id,
        template_archived=template_archived,
    )

    if runtime_status == "missing":
        return "no_active_template"

    if runtime_status == "archived":
        return "template_archived"

    return "ready"
