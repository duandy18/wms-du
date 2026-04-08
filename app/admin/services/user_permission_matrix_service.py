# app/admin/services/user_permission_matrix_service.py
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.admin.contracts.user_permission_matrix import (
    PagePermissionCellOut,
    PermissionMatrixPageOut,
    PermissionMatrixRowOut,
    UserPermissionMatrixOut,
)
from app.user.repositories.navigation_repository import NavigationRepository
from app.user.repositories.user_repository import UserRepository
from app.user.services.user_permissions import get_user_permissions


class UserPermissionMatrixService:
    """
    用户一级页面权限矩阵读取服务：

    目标：
    - 只按一级页面输出矩阵列
    - 二级页面不作为独立授权边界
    - write=true 视为同时具备 read=true（读取时也做归一）

    范围：
    - 只做 matrix 读取
    - 不负责保存
    - 不改动现有 /admin/users 列表与直配权限接口
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.navigation_repo = NavigationRepository(db)
        self.user_repo = UserRepository(db)

    def get_matrix(self) -> UserPermissionMatrixOut:
        root_pages = self._list_root_pages()

        pages = [
            PermissionMatrixPageOut(
                page_code=page["code"],
                page_name=page["name"],
                sort_order=int(page.get("sort_order") or 0),
            )
            for page in root_pages
        ]

        rows = [self._build_user_row(user=user, root_pages=root_pages) for user in self.user_repo.list_users()]

        return UserPermissionMatrixOut(
            pages=pages,
            rows=rows,
        )

    def _list_root_pages(self) -> list[dict[str, Any]]:
        raw_pages = self.navigation_repo.list_pages()

        out: list[dict[str, Any]] = []
        for page in raw_pages:
            level = int(page.get("level") or 0)
            if level != 1:
                continue

            code = str(page.get("code") or "").strip()
            name = str(page.get("name") or "").strip()
            if not code or not name:
                continue

            out.append(
                {
                    "code": code,
                    "name": name,
                    "sort_order": int(page.get("sort_order") or 0),
                    "self_read_permission": page.get("self_read_permission"),
                    "self_write_permission": page.get("self_write_permission"),
                }
            )

        return out

    def _build_user_row(
        self,
        *,
        user: Any,
        root_pages: list[dict[str, Any]],
    ) -> PermissionMatrixRowOut:
        user_permission_names = set(get_user_permissions(self.db, user))

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


__all__ = ["UserPermissionMatrixService"]
