# app/wms/system/read_v1/repos/iam_snapshot_repo.py
from __future__ import annotations

from sqlalchemy.orm import Session, aliased

from app.user.models.page_registry import PageRegistry
from app.user.models.page_route_prefix import PageRoutePrefix
from app.user.models.permission import Permission
from app.user.models.user import User, user_permissions

IamSnapshotUserRow = dict[str, object]
IamSnapshotPermissionRow = dict[str, object]
IamSnapshotUserPermissionRow = dict[str, object]
IamSnapshotPageRow = dict[str, object]
IamSnapshotRoutePrefixRow = dict[str, object]


class WmsIamSnapshotRepo:
    """
    WMS IAM snapshot read repository.

    Boundary:
    - Read only users / permissions / user_permissions / page_registry / page_route_prefixes.
    - Never expose users.password_hash.
    - Do not read wms_service_* tables; service auth is handled by route deps.
    - Do not write any table.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_user_rows(self) -> list[IamSnapshotUserRow]:
        rows = (
            self.db.query(
                User.id.label("user_id"),
                User.username.label("username"),
                User.is_active.label("is_active"),
                User.full_name.label("full_name"),
                User.phone.label("phone"),
                User.email.label("email"),
            )
            .order_by(User.id.asc())
            .all()
        )
        return [dict(row._mapping) for row in rows]

    def list_permission_rows(self) -> list[IamSnapshotPermissionRow]:
        rows = (
            self.db.query(
                Permission.id.label("permission_id"),
                Permission.name.label("permission_code"),
            )
            .order_by(Permission.id.asc())
            .all()
        )
        return [dict(row._mapping) for row in rows]

    def list_user_permission_rows(self) -> list[IamSnapshotUserPermissionRow]:
        rows = (
            self.db.query(
                user_permissions.c.user_id.label("user_id"),
                user_permissions.c.permission_id.label("permission_id"),
                Permission.name.label("permission_code"),
                user_permissions.c.granted_at.label("granted_at"),
            )
            .join(Permission, Permission.id == user_permissions.c.permission_id)
            .order_by(
                user_permissions.c.user_id.asc(),
                Permission.name.asc(),
                user_permissions.c.permission_id.asc(),
            )
            .all()
        )
        return [dict(row._mapping) for row in rows]

    def list_page_rows(self) -> list[IamSnapshotPageRow]:
        page = PageRegistry
        read_permission = aliased(Permission)
        write_permission = aliased(Permission)

        rows = (
            self.db.query(
                page.code.label("page_code"),
                page.name.label("page_name"),
                page.parent_code.label("parent_page_code"),
                page.level.label("level"),
                page.domain_code.label("domain_code"),
                page.show_in_topbar.label("show_in_topbar"),
                page.show_in_sidebar.label("show_in_sidebar"),
                page.inherit_permissions.label("inherit_permissions"),
                read_permission.name.label("read_permission_code"),
                write_permission.name.label("write_permission_code"),
                page.sort_order.label("sort_order"),
                page.is_active.label("is_active"),
            )
            .outerjoin(read_permission, read_permission.id == page.read_permission_id)
            .outerjoin(write_permission, write_permission.id == page.write_permission_id)
            .order_by(page.level.asc(), page.sort_order.asc(), page.code.asc())
            .all()
        )
        return [dict(row._mapping) for row in rows]

    def list_route_prefix_rows(self) -> list[IamSnapshotRoutePrefixRow]:
        rows = (
            self.db.query(
                PageRoutePrefix.id.label("id"),
                PageRoutePrefix.page_code.label("page_code"),
                PageRoutePrefix.route_prefix.label("route_prefix"),
                PageRoutePrefix.sort_order.label("sort_order"),
                PageRoutePrefix.is_active.label("is_active"),
            )
            .order_by(
                PageRoutePrefix.page_code.asc(),
                PageRoutePrefix.is_active.desc(),
                PageRoutePrefix.sort_order.asc(),
                PageRoutePrefix.route_prefix.asc(),
            )
            .all()
        )
        return [dict(row._mapping) for row in rows]


__all__ = [
    "IamSnapshotPageRow",
    "IamSnapshotPermissionRow",
    "IamSnapshotRoutePrefixRow",
    "IamSnapshotUserPermissionRow",
    "IamSnapshotUserRow",
    "WmsIamSnapshotRepo",
]
