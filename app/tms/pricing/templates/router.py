from __future__ import annotations

from fastapi import APIRouter

from .groups.routes import router as groups_router
from .matrix.routes import router as matrix_router
from .ranges.routes import router as ranges_router
from .read.detail_routes import register_detail_routes
from .read.list_routes import register_list_routes
from .surcharge_configs.routes import router as surcharge_router
from .write.router import register as register_write_routes

router = APIRouter(tags=["shipping-assist-pricing-templates"])

register_list_routes(router)
register_detail_routes(router)
register_write_routes(router)

router.include_router(ranges_router)
router.include_router(groups_router)
router.include_router(matrix_router)
router.include_router(surcharge_router)
