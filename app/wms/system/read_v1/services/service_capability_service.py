# app/wms/system/read_v1/services/service_capability_service.py
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime

from app.wms.system.read_v1.contracts import (
    WmsSystemServiceCapabilitiesOut,
    WmsSystemServiceCapabilityOut,
    WmsSystemServiceCapabilityRouteOut,
)
from app.wms.system.read_v1.repos import (
    ServiceCapabilityRouteRow,
    ServiceCapabilityRow,
    WmsServiceCapabilityReadRepo,
)

WMS_APP_CODE = "wms"
WMS_APP_NAME = "仓储管理"


def _optional_str(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _required_str(value: object, *, field_name: str) -> str:
    text = _optional_str(value)
    if text is None:
        raise ValueError(f"{field_name} is required")
    return text


def _bool_value(value: object, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value

    raise ValueError(f"{field_name} must be boolean")


def _datetime_or_none(value: object, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value

    raise ValueError(f"{field_name} must be datetime")


class WmsServiceCapabilityReadService:
    """
    Build WMS service capabilities declaration for ERP sync.

    Boundary:
    - WMS declares what WMS provides.
    - ERP reads this declaration; ERP must not guess WMS capabilities.
    - This service does not expose grants, approvals, written status, or verification status.
    """

    def __init__(self, repo: WmsServiceCapabilityReadRepo) -> None:
        self.repo = repo

    def get_service_capabilities(self) -> WmsSystemServiceCapabilitiesOut:
        capability_rows = self.repo.list_capability_rows()
        route_rows = self.repo.list_route_rows()
        route_rows_by_capability = self._group_route_rows_by_capability(route_rows)

        return WmsSystemServiceCapabilitiesOut(
            app_code=WMS_APP_CODE,
            app_name=WMS_APP_NAME,
            capabilities=[
                self._build_capability_out(
                    row=row,
                    route_rows_by_capability=route_rows_by_capability,
                )
                for row in capability_rows
            ],
        )

    @staticmethod
    def _group_route_rows_by_capability(
        route_rows: list[ServiceCapabilityRouteRow],
    ) -> dict[str, list[ServiceCapabilityRouteRow]]:
        grouped: dict[str, list[ServiceCapabilityRouteRow]] = defaultdict(list)

        for row in route_rows:
            capability_code = _optional_str(row.get("capability_code"))
            if capability_code is None:
                continue
            grouped[capability_code].append(row)

        return dict(grouped)

    def _build_capability_out(
        self,
        *,
        row: ServiceCapabilityRow,
        route_rows_by_capability: Mapping[str, list[ServiceCapabilityRouteRow]],
    ) -> WmsSystemServiceCapabilityOut:
        capability_code = _required_str(
            row.get("capability_code"),
            field_name="capability_code",
        )

        return WmsSystemServiceCapabilityOut(
            capability_code=capability_code,
            capability_name=_required_str(
                row.get("capability_name"),
                field_name="capability_name",
            ),
            resource_code=_required_str(
                row.get("resource_code"),
                field_name="resource_code",
            ),
            permission_code=capability_code,
            description=_optional_str(row.get("description")),
            is_active=_bool_value(row.get("is_active"), field_name="is_active"),
            source_updated_at=_datetime_or_none(
                row.get("source_updated_at"),
                field_name="source_updated_at",
            ),
            routes=[
                self._build_route_out(route_row)
                for route_row in route_rows_by_capability.get(capability_code, [])
            ],
        )

    @staticmethod
    def _build_route_out(
        row: ServiceCapabilityRouteRow,
    ) -> WmsSystemServiceCapabilityRouteOut:
        return WmsSystemServiceCapabilityRouteOut(
            http_method=_required_str(row.get("http_method"), field_name="http_method"),
            path=_required_str(row.get("route_path"), field_name="route_path"),
            route_name=_required_str(row.get("route_name"), field_name="route_name"),
            auth_required=_bool_value(
                row.get("auth_required"),
                field_name="auth_required",
            ),
            is_active=_bool_value(row.get("is_active"), field_name="is_active"),
            source_created_at=_datetime_or_none(
                row.get("source_created_at"),
                field_name="source_created_at",
            ),
        )


__all__ = [
    "WMS_APP_CODE",
    "WMS_APP_NAME",
    "WmsServiceCapabilityReadService",
]
