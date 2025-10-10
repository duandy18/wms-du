from fastapi import APIRouter

from app.api.endpoints import diag, orders, stock

api_router = APIRouter()
api_router.include_router(diag.router)
api_router.include_router(stock.router)
api_router.include_router(orders.router)
