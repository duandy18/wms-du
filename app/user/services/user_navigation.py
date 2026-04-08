# app/user/services/user_navigation.py
from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from app.user.repositories.navigation_repository import NavigationRepository
from app.user.services.user_permissions import get_user_permissions


class UserNavigationService:
    """
    当前用户导航服务：
    - 读取页面与 route_prefix 基础数据
    - 递归计算 effective permission
    - 过滤当前用户无读权限页面
    - 按父子结构返回页面树（支持三级）
    """

    def __init__(self, db: Session):
        self.db = db
        self.repo = NavigationRepository(db)

    @staticmethod
    def _to_page_node(
        row: dict[str, Any],
        *,
        effective_read_permission: str | None,
        effective_write_permission: str | None,
    ) -> dict[str, Any]:
        return {
            "code": row["code"],
            "name": row["name"],
            "parent_code": row.get("parent_code"),
            "level": int(row["level"]),
            "domain_code": row["domain_code"],
            "show_in_topbar": bool(row["show_in_topbar"]),
            "show_in_sidebar": bool(row["show_in_sidebar"]),
            "sort_order": int(row["sort_order"]),
            "is_active": bool(row["is_active"]),
            "inherit_permissions": bool(row["inherit_permissions"]),
            "effective_read_permission": effective_read_permission,
            "effective_write_permission": effective_write_permission,
            "children": [],
        }

    @staticmethod
    def _page_sort_key(node: dict[str, Any]) -> tuple[int, str]:
        return (int(node["sort_order"]), str(node["code"]))

    @classmethod
    def _resolve_effective_permissions(
        cls,
        *,
        code: str,
        rows_by_code: dict[str, dict[str, Any]],
        cache: dict[str, tuple[str | None, str | None]],
        visiting: set[str] | None = None,
    ) -> tuple[str | None, str | None]:
        cached = cache.get(code)
        if cached is not None:
            return cached

        row = rows_by_code.get(code)
        if not row:
            result = (None, None)
            cache[code] = result
            return result

        if not bool(row.get("inherit_permissions")):
            result = (
                row.get("self_read_permission"),
                row.get("self_write_permission"),
            )
            cache[code] = result
            return result

        parent_code = row.get("parent_code")
        if not parent_code:
            result = (None, None)
            cache[code] = result
            return result

        if visiting is None:
            visiting = set()

        if code in visiting:
            result = (None, None)
            cache[code] = result
            return result

        visiting.add(code)
        result = cls._resolve_effective_permissions(
            code=str(parent_code),
            rows_by_code=rows_by_code,
            cache=cache,
            visiting=visiting,
        )
        visiting.remove(code)

        cache[code] = result
        return result

    def get_my_navigation(self, user: Any) -> dict[str, Any]:
        user_permissions = set(get_user_permissions(self.db, user))
        page_rows = self.repo.list_pages()
        rows_by_code = {str(row["code"]): row for row in page_rows}
        permission_cache: dict[str, tuple[str | None, str | None]] = {}

        visible_pages_by_code: dict[str, dict[str, Any]] = {}

        for row in page_rows:
            code = str(row["code"])

            effective_read_permission, effective_write_permission = self._resolve_effective_permissions(
                code=code,
                rows_by_code=rows_by_code,
                cache=permission_cache,
            )

            if not effective_read_permission or effective_read_permission not in user_permissions:
                continue

            node = self._to_page_node(
                row,
                effective_read_permission=effective_read_permission,
                effective_write_permission=effective_write_permission,
            )
            visible_pages_by_code[code] = node

        children_by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for node in visible_pages_by_code.values():
            parent_code = node.get("parent_code")
            if parent_code and parent_code in visible_pages_by_code:
                children_by_parent[str(parent_code)].append(node)

        for parent_code, children in children_by_parent.items():
            children.sort(key=self._page_sort_key)
            visible_pages_by_code[parent_code]["children"] = children

        # 新合同：不再按“无子页则隐藏”做运行时推断
        pages = [
            node
            for node in visible_pages_by_code.values()
            if int(node["level"]) == 1
        ]
        pages.sort(key=self._page_sort_key)

        visible_page_codes = set(visible_pages_by_code.keys())
        route_prefix_rows = self.repo.list_route_prefixes(page_codes=visible_page_codes)
        route_prefixes: list[dict[str, Any]] = []

        for row in route_prefix_rows:
            page = visible_pages_by_code.get(str(row["page_code"]))
            if not page:
                continue

            route_prefixes.append(
                {
                    "route_prefix": row["route_prefix"],
                    "page_code": row["page_code"],
                    "sort_order": int(row["sort_order"]),
                    "is_active": bool(row["is_active"]),
                    "effective_read_permission": page["effective_read_permission"],
                    "effective_write_permission": page["effective_write_permission"],
                }
            )

        return {
            "pages": pages,
            "route_prefixes": route_prefixes,
        }


__all__ = ["UserNavigationService"]
