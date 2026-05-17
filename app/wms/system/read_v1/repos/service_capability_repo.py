# app/wms/system/read_v1/repos/service_capability_repo.py
from __future__ import annotations

from app.wms.system.service_auth.models import (
    WmsServiceCapability,
    WmsServiceCapabilityRoute,
)
from sqlalchemy.orm import Session

ServiceCapabilityRow = dict[str, object]
ServiceCapabilityRouteRow = dict[str, object]


class WmsServiceCapabilityReadRepo:
    """
    WMS service capability read repository.

    Boundary:
    - Read only WMS local service auth declaration tables.
    - Do not read ERP tables.
    - Do not infer capabilities from runtime routes.
    - Do not write any table.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_capability_rows(self) -> list[ServiceCapabilityRow]:
        rows = (
            self.db.query(
                WmsServiceCapability.capability_code.label("capability_code"),
                WmsServiceCapability.capability_name.label("capability_name"),
                WmsServiceCapability.resource_code.label("resource_code"),
                WmsServiceCapability.description.label("description"),
                WmsServiceCapability.is_active.label("is_active"),
                WmsServiceCapability.updated_at.label("source_updated_at"),
            )
            .order_by(WmsServiceCapability.capability_code.asc())
            .all()
        )

        return [dict(row._mapping) for row in rows]

    def list_route_rows(self) -> list[ServiceCapabilityRouteRow]:
        rows = (
            self.db.query(
                WmsServiceCapabilityRoute.capability_code.label("capability_code"),
                WmsServiceCapabilityRoute.http_method.label("http_method"),
                WmsServiceCapabilityRoute.route_path.label("route_path"),
                WmsServiceCapabilityRoute.route_name.label("route_name"),
                WmsServiceCapabilityRoute.auth_required.label("auth_required"),
                WmsServiceCapabilityRoute.is_active.label("is_active"),
                WmsServiceCapabilityRoute.created_at.label("source_created_at"),
            )
            .order_by(
                WmsServiceCapabilityRoute.capability_code.asc(),
                WmsServiceCapabilityRoute.http_method.asc(),
                WmsServiceCapabilityRoute.route_path.asc(),
            )
            .all()
        )

        return [dict(row._mapping) for row in rows]


__all__ = [
    "ServiceCapabilityRow",
    "ServiceCapabilityRouteRow",
    "WmsServiceCapabilityReadRepo",
]
