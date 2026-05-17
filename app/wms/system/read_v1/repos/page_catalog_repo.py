# app/wms/system/read_v1/repos/page_catalog_repo.py
from __future__ import annotations

from sqlalchemy.orm import Session, aliased

from app.user.models.page_registry import PageRegistry
from app.user.models.page_route_prefix import PageRoutePrefix
from app.user.models.permission import Permission

PageCatalogPageRow = dict[str, object]
PageCatalogRoutePrefixRow = dict[str, object]


class WmsPageCatalogRepo:
    """
    WMS page catalog read repository.

    Boundary:
    - Read only page_registry / page_route_prefixes / permissions.
    - Do not read frontend routes.
    - Do not write any table.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_page_rows(self) -> list[PageCatalogPageRow]:
        page = PageRegistry
        self_read = aliased(Permission)
        self_write = aliased(Permission)

        rows = (
            self.db.query(
                page.code.label("page_code"),
                page.name.label("page_name"),
                page.parent_code.label("parent_page_code"),
                page.level.label("level"),
                page.sort_order.label("sort_order"),
                page.is_active.label("is_active"),
                page.inherit_permissions.label("inherit_permissions"),
                self_read.name.label("self_read_permission_code"),
                self_write.name.label("self_write_permission_code"),
            )
            .outerjoin(self_read, self_read.id == page.read_permission_id)
            .outerjoin(self_write, self_write.id == page.write_permission_id)
            .order_by(page.level.asc(), page.sort_order.asc(), page.code.asc())
            .all()
        )

        return [dict(row._mapping) for row in rows]

    def list_route_prefix_rows(self) -> list[PageCatalogRoutePrefixRow]:
        rows = (
            self.db.query(
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
    "PageCatalogPageRow",
    "PageCatalogRoutePrefixRow",
    "WmsPageCatalogRepo",
]
