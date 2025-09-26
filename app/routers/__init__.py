from fastapi import APIRouter

router = APIRouter()

# Example of including sub-routers:
# from .orders import router as orders_router
# router.include_router(orders_router, prefix="/orders", tags=["orders"])
