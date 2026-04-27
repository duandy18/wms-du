# Module split: OMS order facts own native-to-platform_order_lines bridges and fact-level order flows.
from fastapi import APIRouter

from app.oms.order_facts.pdd.router_fact_bridge import router as pdd_fact_bridge_router

router = APIRouter(tags=["oms-order-facts"])

router.include_router(pdd_fact_bridge_router)
