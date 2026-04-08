# app/admin/services/user_permission_matrix_write_service.py
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.admin.contracts.user_permission_matrix import (
    PagePermissionCellOut,
    PermissionMatrixRowOut,
)
from app.admin.contracts.user_permission_matrix_update import UserPermissionMatrixUpdateIn
from app.models.permission import Permission
from app.user.repositories.navigation_repository import NavigationRepository
from app.user.repositories.user_repository import UserRepository
from app.user.services.user_admin_audit import AdminUserAuditService
from app.user.services.user_errors import NotFoundError
from app.user.services.user_permissions import get_user_permissions

ADMIN_WRITE_PERMISSION = "page.admin.write"
STALE_MATRIX_MESSAGE = "矩阵列已过期，请刷新页面后重试"


class UserPermissionMatrixWriteService:
    """
    用户一级页面权限矩阵保存服务：

    规则：
    - 只管理真正可授权的一级页面对应的自有 read/write 权限
    - 保存请求必须带回当前矩阵列集合（page_codes）
    - 若前端列集落后于后端列集，则拒绝保存
    - write=true 自动补 read=true
    - 非一级页面 code 直接报错
    - 非页面权限不受影响，保留原样
    - 不能移除当前登录用户自己的 page.admin.write
    - 不能移除最后一个仍拥有 page.admin.write 的有效用户
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.navigation_repo = NavigationRepository(db)
        self.user_repo = UserRepository(db)
        self.admin_audit = AdminUserAuditService(db)

    def update_matrix_for_user(
        self,
        *,
        user_id: int,
        actor_user_id: int,
        body: UserPermissionMatrixUpdateIn,
    ) -> PermissionMatrixRowOut:
        user = self.user_repo.get_user_by_id(user_id)
        if not user:
            raise NotFoundError("用户不存在")

        root_pages = self._list_root_pages()
        expected_page_codes = [page["code"] for page in root_pages]
        self._ensure_page_codes_match(
            expected_page_codes=expected_page_codes,
            incoming_page_codes=body.page_codes,
        )

        page_by_code = {page["code"]: page for page in root_pages}

        incoming_cell_page_codes = set(body.pages.keys())
        unknown_page_codes = sorted(
            code for code in incoming_cell_page_codes if code not in page_by_code
        )
        if unknown_page_codes:
            raise ValueError(f"非法一级页面: {unknown_page_codes}")

        current_permission_names = set(get_user_permissions(self.db, user))
        managed_permission_names = self._collect_managed_permission_names(root_pages)

        before_row = self._build_user_row(
            user=user,
            root_pages=root_pages,
            user_permission_names=current_permission_names,
        )

        preserved_permission_names = {
            name for name in current_permission_names if name not in managed_permission_names
        }
        desired_managed_permission_names = self._build_desired_managed_permission_names(
            root_pages=root_pages,
            body=body,
        )

        final_permission_names = preserved_permission_names | desired_managed_permission_names

        self._guard_admin_write_lockout(
            user=user,
            actor_user_id=actor_user_id,
            current_permission_names=current_permission_names,
            final_permission_names=final_permission_names,
        )

        final_permission_ids = self._resolve_permission_ids_by_names(final_permission_names)

        updated_user = self.user_repo.replace_user_permissions(
            user_id=int(user.id),
            permission_ids=final_permission_ids,
        )

        updated_permission_names = set(get_user_permissions(self.db, updated_user))
        after_row = self._build_user_row(
            user=updated_user,
            root_pages=root_pages,
            user_permission_names=updated_permission_names,
        )

        self.admin_audit.write_permission_matrix_updated(
            actor_user_id=int(actor_user_id),
            target_user_id=int(updated_user.id),
            target_username=str(updated_user.username),
            before_row=before_row,
            after_row=after_row,
        )

        return after_row

    def _ensure_page_codes_match(
        self,
        *,
        expected_page_codes: list[str],
        incoming_page_codes: list[str],
    ) -> None:
        expected_sorted = sorted(expected_page_codes)
        incoming_sorted = sorted(self._normalize_page_codes(incoming_page_codes))

        if incoming_sorted == expected_sorted:
            return

        expected_set = set(expected_sorted)
        incoming_set = set(incoming_sorted)

        missing = sorted(code for code in expected_sorted if code not in incoming_set)
        extra = sorted(code for code in incoming_sorted if code not in expected_set)

        raise ValueError(
            f"{STALE_MATRIX_MESSAGE} 缺失列={missing} 多余列={extra}"
        )

    def _normalize_page_codes(self, page_codes: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()

        for raw in page_codes:
            code = str(raw or "").strip()
            if not code:
                continue
            if code in seen:
                continue
            seen.add(code)
            out.append(code)

        return out

    def _guard_admin_write_lockout(
        self,
        *,
        user: Any,
        actor_user_id: int,
        current_permission_names: set[str],
        final_permission_names: set[str],
    ) -> None:
        current_has_admin_write = ADMIN_WRITE_PERMISSION in current_permission_names
        final_has_admin_write = ADMIN_WRITE_PERMISSION in final_permission_names
        target_is_active = bool(getattr(user, "is_active", True))

        if (
            int(actor_user_id) == int(user.id)
            and current_has_admin_write
            and not final_has_admin_write
        ):
            raise ValueError("不能移除当前登录用户自己的 page.admin.write")

        if target_is_active and current_has_admin_write and not final_has_admin_write:
            active_admin_write_count = self.user_repo.count_active_users_with_permission(
                ADMIN_WRITE_PERMISSION
            )
            if active_admin_write_count <= 1:
                raise ValueError("不能移除最后一个仍拥有 page.admin.write 的有效用户")

    def _list_root_pages(self) -> list[dict[str, Any]]:
        raw_pages = self.navigation_repo.list_pages()

        out: list[dict[str, Any]] = []
        for page in raw_pages:
            if not self._is_grantable_root_page(page):
                continue

            out.append(
                {
                    "code": str(page["code"]).strip(),
                    "name": str(page["name"]).strip(),
                    "sort_order": int(page.get("sort_order") or 0),
                    "self_read_permission": page.get("self_read_permission"),
                    "self_write_permission": page.get("self_write_permission"),
                }
            )

        return out

    def _is_grantable_root_page(self, page: dict[str, Any]) -> bool:
        level = int(page.get("level") or 0)
        if level != 1:
            return False

        code = str(page.get("code") or "").strip()
        name = str(page.get("name") or "").strip()
        if not code or not name:
            return False

        if bool(page.get("inherit_permissions")):
            return False

        read_permission = page.get("self_read_permission")
        write_permission = page.get("self_write_permission")

        if not isinstance(read_permission, str) or not read_permission.strip():
            return False
        if not isinstance(write_permission, str) or not write_permission.strip():
            return False

        return True

    def _collect_managed_permission_names(self, root_pages: list[dict[str, Any]]) -> set[str]:
        out: set[str] = set()
        for page in root_pages:
            read_permission = page.get("self_read_permission")
            write_permission = page.get("self_write_permission")
            if isinstance(read_permission, str) and read_permission:
                out.add(read_permission)
            if isinstance(write_permission, str) and write_permission:
                out.add(write_permission)
        return out

    def _build_desired_managed_permission_names(
        self,
        *,
        root_pages: list[dict[str, Any]],
        body: UserPermissionMatrixUpdateIn,
    ) -> set[str]:
        out: set[str] = set()

        for page in root_pages:
            code = page["code"]
            cell = body.pages.get(code)

            want_read = bool(cell.read) if cell is not None else False
            want_write = bool(cell.write) if cell is not None else False

            if want_write:
                want_read = True

            read_permission = page.get("self_read_permission")
            write_permission = page.get("self_write_permission")

            if want_read and isinstance(read_permission, str) and read_permission:
                out.add(read_permission)
            if want_write and isinstance(write_permission, str) and write_permission:
                out.add(write_permission)

        return out

    def _resolve_permission_ids_by_names(self, permission_names: set[str]) -> list[int]:
        if not permission_names:
            return []

        rows = (
            self.db.query(Permission)
            .filter(Permission.name.in_(sorted(permission_names)))
            .all()
        )
        by_name = {str(row.name): int(row.id) for row in rows}

        missing = sorted(name for name in permission_names if name not in by_name)
        if missing:
            raise ValueError(f"权限不存在: {missing}")

        return [by_name[name] for name in sorted(permission_names)]

    def _build_user_row(
        self,
        *,
        user: Any,
        root_pages: list[dict[str, Any]],
        user_permission_names: set[str],
    ) -> PermissionMatrixRowOut:
        page_cells: dict[str, PagePermissionCellOut] = {}
        for page in root_pages:
            page_cells[page["code"]] = self._build_page_cell(
                page=page,
                user_permission_names=user_permission_names,
            )

        return PermissionMatrixRowOut(
            user_id=int(user.id),
            username=str(user.username),
            full_name=getattr(user, "full_name", None),
            is_active=bool(getattr(user, "is_active", True)),
            pages=page_cells,
        )

    def _build_page_cell(
        self,
        *,
        page: dict[str, Any],
        user_permission_names: set[str],
    ) -> PagePermissionCellOut:
        read_permission = page.get("self_read_permission")
        write_permission = page.get("self_write_permission")

        has_write = isinstance(write_permission, str) and write_permission in user_permission_names
        has_read = has_write or (
            isinstance(read_permission, str) and read_permission in user_permission_names
        )

        return PagePermissionCellOut(
            read=has_read,
            write=has_write,
        )


__all__ = ["UserPermissionMatrixWriteService"]
