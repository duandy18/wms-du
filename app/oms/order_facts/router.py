from fastapi import APIRouter

from app.oms.order_facts.router_platform_order_mirrors import (
    router as platform_order_mirrors_router,
)


router = APIRouter()

# Collector 分离后，OMS 不再保留旧平台采集事实桥接。
# 当前模块承载 OMS 自有的平台订单镜像与后续履约订单转化入口。
router.include_router(platform_order_mirrors_router)
