# app/tms/providers/mappers.py
from __future__ import annotations

from typing import Any

from .contracts import ShippingProviderContactOut, ShippingProviderOut


def row_to_contact(row: Any) -> ShippingProviderContactOut:
    return ShippingProviderContactOut(
        id=row["id"],
        shipping_provider_id=row["shipping_provider_id"],
        name=row["name"],
        phone=row.get("phone"),
        email=row.get("email"),
        wechat=row.get("wechat"),
        role=row.get("role") or "other",
        is_primary=bool(row.get("is_primary", False)),
        active=bool(row.get("active", True)),
    )


def row_to_provider(row: Any, contacts: list[ShippingProviderContactOut]) -> ShippingProviderOut:
    name = row["name"]
    display = name

    return ShippingProviderOut(
        id=row["id"],
        name=name,
        code=row["code"],
        display_label=display,
        company_code=row.get("company_code"),
        resource_code=row.get("resource_code"),
        address=row.get("address"),
        active=row.get("active", True),
        priority=row.get("priority", 100),
        contacts=contacts,
    )
