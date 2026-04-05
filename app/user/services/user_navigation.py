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
    - 计算 effective permission
    - 过滤当前用户无读权限页面
    - 按父子结构返回页面树
    """

    def __init__(self, db: Session):
        self.db = db
        self.repo = NavigationRepository(db)

    @staticmethod
    def _effective_read_permission(row: dict[str, Any]) -> str | None:
        if row.get("inherit_permissions"):
            return row.get("parent_read_permission")
        return row.get("self_read_permission")

    @staticmethod
    def _effective_write_permission(row: dict[str, Any]) -> str | None:
        if row.get("inherit_permissions"):
            return row.get("parent_write_permission")
        return row.get("self_write_permission")

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

    def get_my_navigation(self, user: Any) -> dict[str, Any]:
        user_permissions = set(get_user_permissions(self.db, user))
        page_rows = self.repo.list_pages()

        visible_parents: dict[str, dict[str, Any]] = {}
        visible_pages_by_code: dict[str, dict[str, Any]] = {}
        children_by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)
        parent_order: list[str] = []

        for row in page_rows:
            effective_read_permission = self._effective_read_permission(row)
            effective_write_permission = self._effective_write_permission(row)

            # 当前阶段：没有 effective_read_permission，就视为不可见
            if not effective_read_permission or effective_read_permission not in user_permissions:
                continue

            node = self._to_page_node(
                row,
                effective_read_permission=effective_read_permission,
                effective_write_permission=effective_write_permission,
            )
            visible_pages_by_code[node["code"]] = node

            if node["level"] == 1:
                visible_parents[node["code"]] = node
                parent_order.append(node["code"])
            elif node["level"] == 2 and node["parent_code"]:
                children_by_parent[node["parent_code"]].append(node)

        pages: list[dict[str, Any]] = []

        for parent_code in parent_order:
            parent = visible_parents[parent_code]
            children = children_by_parent.get(parent_code, [])

            # 当前主线：一级页面没有任何可见子页时隐藏
            if not children:
                continue

            parent["children"] = children
            pages.append(parent)

        visible_page_codes = {page["code"] for page in visible_pages_by_code.values()}

        route_prefix_rows = self.repo.list_route_prefixes(page_codes=visible_page_codes)
        route_prefixes: list[dict[str, Any]] = []

        for row in route_prefix_rows:
            page = visible_pages_by_code.get(row["page_code"])
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
