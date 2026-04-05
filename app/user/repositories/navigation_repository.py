# app/user/repositories/navigation_repository.py
from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy.orm import Session, aliased

from app.models.page_registry import PageRegistry
from app.models.page_route_prefix import PageRoutePrefix
from app.models.permission import Permission


class NavigationRepository:
    """
    导航数据读取仓库：
    - 只负责读取页面与 route_prefix 基础数据
    - 不负责用户权限过滤
    - 不负责页面树组装
    """

    def __init__(self, db: Session):
        self.db = db

    def list_pages(self) -> list[dict[str, Any]]:
        page = PageRegistry
        parent = aliased(PageRegistry)

        self_read = aliased(Permission)
        self_write = aliased(Permission)
        parent_read = aliased(Permission)
        parent_write = aliased(Permission)

        rows = (
            self.db.query(
                page.code.label("code"),
                page.name.label("name"),
                page.parent_code.label("parent_code"),
                page.level.label("level"),
                page.domain_code.label("domain_code"),
                page.show_in_topbar.label("show_in_topbar"),
                page.show_in_sidebar.label("show_in_sidebar"),
                page.sort_order.label("sort_order"),
                page.is_active.label("is_active"),
                page.inherit_permissions.label("inherit_permissions"),
                self_read.name.label("self_read_permission"),
                self_write.name.label("self_write_permission"),
                parent_read.name.label("parent_read_permission"),
                parent_write.name.label("parent_write_permission"),
            )
            .outerjoin(parent, parent.code == page.parent_code)
            .outerjoin(self_read, self_read.id == page.read_permission_id)
            .outerjoin(self_write, self_write.id == page.write_permission_id)
            .outerjoin(parent_read, parent_read.id == parent.read_permission_id)
            .outerjoin(parent_write, parent_write.id == parent.write_permission_id)
            .filter(page.is_active.is_(True))
            .order_by(page.level.asc(), page.sort_order.asc(), page.code.asc())
            .all()
        )

        return [dict(row._mapping) for row in rows]

    def list_route_prefixes(
        self,
        *,
        page_codes: Iterable[str] | None = None,
    ) -> list[dict[str, Any]]:
        query = (
            self.db.query(
                PageRoutePrefix.route_prefix.label("route_prefix"),
                PageRoutePrefix.page_code.label("page_code"),
                PageRoutePrefix.sort_order.label("sort_order"),
                PageRoutePrefix.is_active.label("is_active"),
            )
            .filter(PageRoutePrefix.is_active.is_(True))
            .order_by(PageRoutePrefix.sort_order.asc(), PageRoutePrefix.route_prefix.asc())
        )

        if page_codes is not None:
            page_code_list = [code for code in page_codes if code]
            if not page_code_list:
                return []
            query = query.filter(PageRoutePrefix.page_code.in_(page_code_list))

        rows = query.all()
        return [dict(row._mapping) for row in rows]


__all__ = ["NavigationRepository"]
