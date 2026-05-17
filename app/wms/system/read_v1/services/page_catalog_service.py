# app/wms/system/read_v1/services/page_catalog_service.py
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping

from app.wms.system.read_v1.contracts import (
    WmsSystemPageCatalogOut,
    WmsSystemPageCatalogPageOut,
)
from app.wms.system.read_v1.repos import (
    PageCatalogPageRow,
    PageCatalogRoutePrefixRow,
    WmsPageCatalogRepo,
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


class WmsPageCatalogService:
    """
    Build WMS page catalog for ERP projection sync.

    Boundary:
    - WMS is the source of truth for its own page catalog.
    - ERP must not connect to WMS DB directly.
    - ERP must not infer WMS pages from frontend routes.
    """

    def __init__(self, repo: WmsPageCatalogRepo) -> None:
        self.repo = repo

    def get_page_catalog(self) -> WmsSystemPageCatalogOut:
        page_rows = self.repo.list_page_rows()
        route_rows = self.repo.list_route_prefix_rows()

        rows_by_code = {
            _required_str(row.get("page_code"), field_name="page_code"): row
            for row in page_rows
        }
        route_rows_by_page = self._group_route_rows_by_page(route_rows)
        permission_cache: dict[str, tuple[str | None, str | None]] = {}

        pages = [
            self._build_page_out(
                row=row,
                rows_by_code=rows_by_code,
                route_rows_by_page=route_rows_by_page,
                permission_cache=permission_cache,
            )
            for row in page_rows
        ]

        return WmsSystemPageCatalogOut(
            app_code=WMS_APP_CODE,
            app_name=WMS_APP_NAME,
            pages=pages,
        )

    @staticmethod
    def _group_route_rows_by_page(
        route_rows: list[PageCatalogRoutePrefixRow],
    ) -> dict[str, list[PageCatalogRoutePrefixRow]]:
        grouped: dict[str, list[PageCatalogRoutePrefixRow]] = defaultdict(list)

        for row in route_rows:
            page_code = _optional_str(row.get("page_code"))
            if page_code is None:
                continue
            grouped[page_code].append(row)

        return dict(grouped)

    def _build_page_out(
        self,
        *,
        row: PageCatalogPageRow,
        rows_by_code: Mapping[str, PageCatalogPageRow],
        route_rows_by_page: Mapping[str, list[PageCatalogRoutePrefixRow]],
        permission_cache: dict[str, tuple[str | None, str | None]],
    ) -> WmsSystemPageCatalogPageOut:
        page_code = _required_str(row.get("page_code"), field_name="page_code")
        read_permission_code, write_permission_code = self._resolve_effective_permissions(
            page_code=page_code,
            rows_by_code=rows_by_code,
            cache=permission_cache,
        )

        return WmsSystemPageCatalogPageOut(
            page_code=page_code,
            page_name=_required_str(row.get("page_name"), field_name="page_name"),
            route_path=self._select_route_path(
                route_rows_by_page.get(page_code, []),
            ),
            parent_page_code=_optional_str(row.get("parent_page_code")),
            level=_int_value(row.get("level"), field_name="level"),
            read_permission_code=read_permission_code,
            write_permission_code=write_permission_code,
            is_active=_bool_value(row.get("is_active"), field_name="is_active"),
            sort_order=_int_value(row.get("sort_order"), field_name="sort_order"),
            source_updated_at=None,
        )

    @classmethod
    def _resolve_effective_permissions(
        cls,
        *,
        page_code: str,
        rows_by_code: Mapping[str, PageCatalogPageRow],
        cache: dict[str, tuple[str | None, str | None]],
        visiting: set[str] | None = None,
    ) -> tuple[str | None, str | None]:
        cached = cache.get(page_code)
        if cached is not None:
            return cached

        row = rows_by_code.get(page_code)
        if row is None:
            result = (None, None)
            cache[page_code] = result
            return result

        inherit_permissions = _bool_value(
            row.get("inherit_permissions"),
            field_name="inherit_permissions",
        )
        if not inherit_permissions:
            result = (
                _optional_str(row.get("self_read_permission_code")),
                _optional_str(row.get("self_write_permission_code")),
            )
            cache[page_code] = result
            return result

        parent_page_code = _optional_str(row.get("parent_page_code"))
        if parent_page_code is None:
            result = (None, None)
            cache[page_code] = result
            return result

        if visiting is None:
            visiting = set()

        if page_code in visiting:
            result = (None, None)
            cache[page_code] = result
            return result

        visiting.add(page_code)
        result = cls._resolve_effective_permissions(
            page_code=parent_page_code,
            rows_by_code=rows_by_code,
            cache=cache,
            visiting=visiting,
        )
        visiting.remove(page_code)

        cache[page_code] = result
        return result

    @staticmethod
    def _select_route_path(
        route_rows: list[PageCatalogRoutePrefixRow],
    ) -> str | None:
        if not route_rows:
            return None

        active_rows = [
            row
            for row in route_rows
            if _bool_value(row.get("is_active"), field_name="route_is_active")
        ]
        candidates = active_rows or route_rows

        selected = sorted(
            candidates,
            key=lambda item: (
                _int_value(item.get("sort_order"), field_name="route_sort_order"),
                _required_str(item.get("route_prefix"), field_name="route_prefix"),
            ),
        )[0]

        return _required_str(selected.get("route_prefix"), field_name="route_prefix")


__all__ = [
    "WMS_APP_CODE",
    "WMS_APP_NAME",
    "WmsPageCatalogService",
]
