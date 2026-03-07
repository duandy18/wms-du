# app/api/routers/shipping_provider_pricing_schemes_routes_pricing_matrix.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers.shipping_provider_pricing_schemes_routes_pricing_matrix_copy import (
    register_pricing_matrix_copy_routes,
)
from app.api.routers.shipping_provider_pricing_schemes_routes_pricing_matrix_crud import (
    register_pricing_matrix_crud_routes,
)
from app.api.routers.shipping_provider_pricing_schemes_routes_pricing_matrix_matrix_editor import (
    register_pricing_matrix_matrix_editor_routes,
)
from app.api.routers.shipping_provider_pricing_schemes_routes_pricing_matrix_replace import (
    register_pricing_matrix_replace_routes,
)


def register_pricing_matrix_routes(router: APIRouter) -> None:
    # Phase-5：matrix editor view + full matrix patch
    register_pricing_matrix_matrix_editor_routes(router)

    # CRUD: create/update/delete
    register_pricing_matrix_crud_routes(router)

    # Replace: atomic full-set replace for one destination group
    register_pricing_matrix_replace_routes(router)

    # Copy: pricing-matrix:copy
    register_pricing_matrix_copy_routes(router)
