from fastapi import APIRouter

from app.oms.order_facts.router_fsku_mapping_candidates import (
    router as fsku_mapping_candidates_router,
)
from app.oms.order_facts.router_fulfillment_conversion import (
    router as fulfillment_conversion_router,
)
from app.oms.order_facts.router_platform_order_mirrors import (
    router as platform_order_mirrors_router,
)


router = APIRouter()

# Collector 分离后，OMS 不再保留旧平台采集事实桥接。
# 当前模块承载 OMS 自有的平台订单镜像、商品映射候选与履约订单转化入口。
router.include_router(platform_order_mirrors_router)
router.include_router(fsku_mapping_candidates_router)
router.include_router(fulfillment_conversion_router)
