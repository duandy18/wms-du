# app/wms/system/read_v1/services/iam_snapshot_service.py
from __future__ import annotations

from datetime import datetime, timezone

from app.wms.system.read_v1.contracts import (
    WmsSystemIamSnapshotOut,
    WmsSystemIamSnapshotPageOut,
    WmsSystemIamSnapshotPermissionOut,
    WmsSystemIamSnapshotRoutePrefixOut,
    WmsSystemIamSnapshotUserOut,
    WmsSystemIamSnapshotUserPermissionOut,
)
from app.wms.system.read_v1.repos import (
    IamSnapshotPageRow,
    IamSnapshotPermissionRow,
    IamSnapshotRoutePrefixRow,
    IamSnapshotUserPermissionRow,
    IamSnapshotUserRow,
    WmsIamSnapshotRepo,
)
from app.wms.system.read_v1.services.page_catalog_service import WMS_APP_CODE, WMS_APP_NAME


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


def _int_value(value: object, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be integer")

    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be integer") from exc


def _bool_value(value: object, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value

    raise ValueError(f"{field_name} must be boolean")


def _datetime_value(value: object, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return value

    raise ValueError(f"{field_name} must be datetime")


class WmsIamSnapshotService:
    """
    Build WMS IAM snapshot for ERP projection sync.

    Boundary:
    - WMS remains the runtime permission source of truth.
    - ERP gets a read-only projection input.
    - This service never exposes password_hash.
    - This service never writes WMS IAM tables.
    """

    def __init__(self, repo: WmsIamSnapshotRepo) -> None:
        self.repo = repo

    def get_iam_snapshot(self) -> WmsSystemIamSnapshotOut:
        return WmsSystemIamSnapshotOut(
            app_code=WMS_APP_CODE,
            app_name=WMS_APP_NAME,
            snapshot_at=datetime.now(timezone.utc),
            users=[self._build_user_out(row) for row in self.repo.list_user_rows()],
            permissions=[
                self._build_permission_out(row)
                for row in self.repo.list_permission_rows()
            ],
            user_permissions=[
                self._build_user_permission_out(row)
                for row in self.repo.list_user_permission_rows()
            ],
            page_registry=[
                self._build_page_out(row)
                for row in self.repo.list_page_rows()
            ],
            page_route_prefixes=[
                self._build_route_prefix_out(row)
                for row in self.repo.list_route_prefix_rows()
            ],
        )

    @staticmethod
    def _build_user_out(row: IamSnapshotUserRow) -> WmsSystemIamSnapshotUserOut:
        return WmsSystemIamSnapshotUserOut(
            user_id=_int_value(row.get("user_id"), field_name="user_id"),
            username=_required_str(row.get("username"), field_name="username"),
            is_active=_bool_value(row.get("is_active"), field_name="is_active"),
            full_name=_optional_str(row.get("full_name")),
            phone=_optional_str(row.get("phone")),
            email=_optional_str(row.get("email")),
        )

    @staticmethod
    def _build_permission_out(
        row: IamSnapshotPermissionRow,
    ) -> WmsSystemIamSnapshotPermissionOut:
        return WmsSystemIamSnapshotPermissionOut(
            permission_id=_int_value(row.get("permission_id"), field_name="permission_id"),
            permission_code=_required_str(
                row.get("permission_code"),
                field_name="permission_code",
            ),
        )

    @staticmethod
    def _build_user_permission_out(
        row: IamSnapshotUserPermissionRow,
    ) -> WmsSystemIamSnapshotUserPermissionOut:
        return WmsSystemIamSnapshotUserPermissionOut(
            user_id=_int_value(row.get("user_id"), field_name="user_id"),
            permission_id=_int_value(row.get("permission_id"), field_name="permission_id"),
            permission_code=_required_str(
                row.get("permission_code"),
                field_name="permission_code",
            ),
            granted_at=_datetime_value(row.get("granted_at"), field_name="granted_at"),
        )

    @staticmethod
    def _build_page_out(row: IamSnapshotPageRow) -> WmsSystemIamSnapshotPageOut:
        return WmsSystemIamSnapshotPageOut(
            page_code=_required_str(row.get("page_code"), field_name="page_code"),
            page_name=_required_str(row.get("page_name"), field_name="page_name"),
            parent_page_code=_optional_str(row.get("parent_page_code")),
            level=_int_value(row.get("level"), field_name="level"),
            domain_code=_required_str(row.get("domain_code"), field_name="domain_code"),
            show_in_topbar=_bool_value(
                row.get("show_in_topbar"),
                field_name="show_in_topbar",
            ),
            show_in_sidebar=_bool_value(
                row.get("show_in_sidebar"),
                field_name="show_in_sidebar",
            ),
            inherit_permissions=_bool_value(
                row.get("inherit_permissions"),
                field_name="inherit_permissions",
            ),
            read_permission_code=_optional_str(row.get("read_permission_code")),
            write_permission_code=_optional_str(row.get("write_permission_code")),
            sort_order=_int_value(row.get("sort_order"), field_name="sort_order"),
            is_active=_bool_value(row.get("is_active"), field_name="is_active"),
        )

    @staticmethod
    def _build_route_prefix_out(
        row: IamSnapshotRoutePrefixRow,
    ) -> WmsSystemIamSnapshotRoutePrefixOut:
        return WmsSystemIamSnapshotRoutePrefixOut(
            id=_int_value(row.get("id"), field_name="id"),
            page_code=_required_str(row.get("page_code"), field_name="page_code"),
            route_prefix=_required_str(
                row.get("route_prefix"),
                field_name="route_prefix",
            ),
            sort_order=_int_value(row.get("sort_order"), field_name="sort_order"),
            is_active=_bool_value(row.get("is_active"), field_name="is_active"),
        )


__all__ = ["WmsIamSnapshotService"]
