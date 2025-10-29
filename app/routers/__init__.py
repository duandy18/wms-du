# app/routers/__init__.py
from fastapi import APIRouter

from . import stock_ledger

router = APIRouter()
router.include_router(stock_ledger.router)
